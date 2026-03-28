"""Bedrock model pricing with 3-tier fallback and local file caching.

Adapted from multitenancy-and-observability-for-bedrock/backend/shared/pricing.py.
Replaces DynamoDB caching with local file cache using the same hash-based
invalidation pattern as model_capability_validator.py.

Flow:
    1. Check local cache -- if profiles_hash matches, return immediately
    2. Tier 1: Query AWS Price List API (all 3 service codes)
       -> If both input + output found: pricing_source = "api"
    3. Tier 2: If output missing, re-query AmazonBedrockService only
       -> If filled: pricing_source = "api_partial"
    4. Tier 3: Scrape the AWS Bedrock pricing webpage bulk JSON
       -> If filled: pricing_source = "webpage"
    5. If still missing -> "unavailable" with None costs
    6. Cache the result locally in .cache/model_pricing.json
"""

import gzip
import hashlib
import html as html_module
import json
import logging
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import boto3

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths and constants
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).parent.parent
CACHE_DIR = PROJECT_ROOT / ".cache"
PRICING_CACHE_FILE = CACHE_DIR / "model_pricing.json"
MODELS_PROFILE_PATH = PROJECT_ROOT / "config" / "models_profiles.jsonl"
JUDGE_PROFILE_PATH = PROJECT_ROOT / "config" / "judge_profiles.jsonl"

SERVICE_CODES = [
    "AmazonBedrock",
    "AmazonBedrockService",
    "AmazonBedrockFoundationModels",
]
PRICING_CLIENT_REGION = "us-east-1"

# AWS Bedrock pricing page and bulk JSON endpoints
_PRICING_PAGE_URL = "https://aws.amazon.com/bedrock/pricing/"
_BULK_JSON_URL = "https://b0.p.awsstatic.com/pricing/2.0/meteredUnitMaps/{svc}/USD/current/{svc}.json"

# Map service paths from priceOf tokens to bulk JSON service names
_SERVICE_PATH_MAP = {
    "bedrock/bedrock": "bedrock",
    "bedrockfoundationmodels/bedrockfoundationmodels": "bedrockfoundationmodels",
    "bedrockservice/bedrockservice": "bedrockservice",
}

# Region code to display name (as used on the AWS pricing page)
_REGION_DISPLAY_NAMES = {
    "us-east-1": "US East (N. Virginia)",
    "us-east-2": "US East (Ohio)",
    "us-west-1": "US West (N. California)",
    "us-west-2": "US West (Oregon)",
    "af-south-1": "Africa (Cape Town)",
    "ap-east-1": "Asia Pacific (Hong Kong)",
    "ap-east-2": "Asia Pacific (Taipei)",
    "ap-south-1": "Asia Pacific (Mumbai)",
    "ap-south-2": "Asia Pacific (Hyderabad)",
    "ap-southeast-1": "Asia Pacific (Singapore)",
    "ap-southeast-2": "Asia Pacific (Sydney)",
    "ap-southeast-3": "Asia Pacific (Jakarta)",
    "ap-southeast-4": "Asia Pacific (Melbourne)",
    "ap-southeast-5": "Asia Pacific (Malaysia)",
    "ap-southeast-7": "Asia Pacific (Thailand)",
    "ap-northeast-1": "Asia Pacific (Tokyo)",
    "ap-northeast-2": "Asia Pacific (Seoul)",
    "ap-northeast-3": "Asia Pacific (Osaka)",
    "ap-south-3": "Asia Pacific (New Zealand)",
    "ca-central-1": "Canada (Central)",
    "ca-west-1": "Canada West (Calgary)",
    "eu-central-1": "EU (Frankfurt)",
    "eu-central-2": "EU (Zurich)",
    "eu-west-1": "EU (Ireland)",
    "eu-west-2": "EU (London)",
    "eu-west-3": "EU (Paris)",
    "eu-north-1": "EU (Stockholm)",
    "eu-south-1": "EU (Milan)",
    "eu-south-2": "EU (Spain)",
    "me-south-1": "Middle East (Bahrain)",
    "me-central-1": "Middle East (UAE)",
    "mx-central-1": "Mexico (Central)",
    "sa-east-1": "South America (Sao Paulo)",
    "il-central-1": "Israel (Tel Aviv)",
    "us-gov-west-1": "AWS GovCloud (US)",
    "us-gov-east-1": "AWS GovCloud (US-East)",
}


# ---------------------------------------------------------------------------
# Local file cache (mirrors model_capability_validator.py pattern)
# ---------------------------------------------------------------------------

def get_profiles_hash() -> str:
    """Generate SHA256 hash of models_profiles.jsonl + judge_profiles.jsonl content."""
    h = hashlib.sha256()
    for path in (MODELS_PROFILE_PATH, JUDGE_PROFILE_PATH):
        try:
            with open(path, "r", encoding="utf-8") as f:
                h.update(f.read().encode())
        except FileNotFoundError:
            logger.warning("Profile file not found: %s", path)
        except Exception as e:
            logger.error("Error reading profile %s: %s", path, e)
    return h.hexdigest()


def load_pricing_cache() -> dict:
    """Load cached pricing from local JSON file."""
    if not PRICING_CACHE_FILE.exists():
        return {"last_updated": None, "profiles_hash": "", "pricing": {}}
    try:
        with open(PRICING_CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error("Error loading pricing cache: %s", e)
        return {"last_updated": None, "profiles_hash": "", "pricing": {}}


def save_pricing_cache(cache: dict) -> bool:
    """Save pricing cache to local JSON file."""
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache["last_updated"] = datetime.now(timezone.utc).isoformat()
        with open(PRICING_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2)
        logger.info("Pricing cache saved to %s", PRICING_CACHE_FILE)
        return True
    except Exception as e:
        logger.error("Error saving pricing cache: %s", e)
        return False


def is_pricing_cache_valid() -> bool:
    """Check if the pricing cache is still valid (profiles haven't changed)."""
    cache = load_pricing_cache()
    if not cache.get("profiles_hash"):
        return False
    return cache["profiles_hash"] == get_profiles_hash()


# ---------------------------------------------------------------------------
# Model ID helpers
# ---------------------------------------------------------------------------

def strip_model_id_for_pricing(model_id: str) -> str:
    """Strip 'bedrock/' prefix and cross-region prefixes for API lookup.

    Examples:
        bedrock/us.anthropic.claude-sonnet-4-5-20250929-v1:0
            -> anthropic.claude-sonnet-4-5-20250929-v1:0
        bedrock/deepseek.v3-v1:0
            -> deepseek.v3-v1:0
        bedrock/converse/us.amazon.nova-2-lite-v1:0
            -> amazon.nova-2-lite-v1:0
    """
    cleaned = model_id
    for prefix in ("bedrock/converse/", "bedrock/"):
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):]
            break
    # Remove cross-region inference prefixes (us., eu., ap., etc.)
    cleaned = re.sub(r"^[a-z]{2}\.", "", cleaned)
    return cleaned


def _cache_key(model_id: str, region: str) -> str:
    """Build cache key from model_id (without bedrock/ prefix) and region."""
    # Strip bedrock/ but keep cross-region prefix for uniqueness
    stripped = model_id
    for prefix in ("bedrock/converse/", "bedrock/"):
        if stripped.startswith(prefix):
            stripped = stripped[len(prefix):]
            break
    return f"{region}#{stripped}"


# ---------------------------------------------------------------------------
# Pricing API helpers
# ---------------------------------------------------------------------------

def get_all_products(pricing_client, service_code: str) -> list:
    """Paginate through all products for a service code."""
    products = []
    next_token = None
    while True:
        kwargs = {
            "ServiceCode": service_code,
            "MaxResults": 100,
            "FormatVersion": "aws_v1",
        }
        if next_token:
            kwargs["NextToken"] = next_token
        response = pricing_client.get_products(**kwargs)
        for item_json in response.get("PriceList", []):
            products.append(json.loads(item_json))
        next_token = response.get("NextToken")
        if not next_token:
            break
    return products


def extract_pricing(product: dict) -> dict:
    """Extract pricing details from a single product entry."""
    attrs = product.get("product", {}).get("attributes", {})
    terms = product.get("terms", {})

    price_per_unit = None
    for offer in terms.get("OnDemand", {}).values():
        for dim in offer.get("priceDimensions", {}).values():
            price_per_unit = dim.get("pricePerUnit", {}).get("USD")
            break

    return {
        "model_id": attrs.get("modelId", ""),
        "usagetype": attrs.get("usagetype", ""),
        "inference_type": attrs.get("inferenceType", ""),
        "feature": attrs.get("feature", ""),
        "feature_type": attrs.get("featuretype", ""),
        "region_code": attrs.get("regionCode", ""),
        "group_description": attrs.get("groupDescription", ""),
        "price_per_unit_usd": price_per_unit,
    }


def is_on_demand_standard(entry: dict) -> bool:
    """Filter to only on-demand, non-reserved, non-batch, non-cache entries."""
    usagetype = entry["usagetype"].lower()
    feature = entry["feature"].lower()
    feature_type = entry["feature_type"].lower()

    for skip in ("reserved", "batch", "cache", "long-context", "latency-optimized"):
        if skip in usagetype or skip in feature or skip in feature_type:
            return False
    return True


def classify_token_type(entry: dict) -> str:
    """Determine if this is input or output token pricing."""
    usagetype = entry["usagetype"].lower()
    inference_type = entry["inference_type"].lower()
    group_desc = entry["group_description"].lower()

    if "output" in usagetype or "output" in inference_type or "output" in group_desc:
        return "output"
    elif "input" in usagetype or "input" in inference_type or "input" in group_desc:
        return "input"
    return "unknown"


def _matches_model(entry: dict, model_id: str, region: str) -> bool:
    """Check if a pricing entry matches the given model_id and region."""
    if entry["region_code"] and entry["region_code"] != region:
        return False

    # Strip bare trailing version suffix like ":0" that isn't part of a "-vN:N" pattern
    # e.g., "kimi-k2-thinking:0" -> "kimi-k2-thinking"
    # but keep "claude-sonnet-4-5-20250929-v1:0" intact
    clean_id = re.sub(r"(?<!-v\d):(\d+)$", "", model_id)
    model_lower = clean_id.lower()
    entry_model_id = entry.get("model_id", "").lower()
    entry_usagetype = entry.get("usagetype", "").lower()

    if entry_model_id and entry_model_id == model_lower:
        return True
    if model_lower in entry_usagetype:
        return True

    # Normalized substring match (strips dots, dashes, underscores, colons)
    a = re.sub(r"[-._:]", "", model_lower)
    if entry_model_id:
        b = re.sub(r"[-._:]", "", entry_model_id)
        if a in b or b in a:
            return True
    if entry_usagetype:
        b = re.sub(r"[-._:]", "", entry_usagetype)
        if a in b:
            return True

    # Token-overlap match: split on separators and check overlap
    # Handles vendor name mismatches (e.g., "moonshot" vs "moonshotai")
    model_parts = re.split(r"[-._:]", model_lower)
    model_parts = [p for p in model_parts if p]
    if entry_usagetype and len(model_parts) > 1:
        usage_tokens = set(re.split(r"[-._:]", entry_usagetype)) - {""}
        # For "vendor.model-name" format, skip the vendor prefix (first part before ".")
        # and require all remaining tokens to appear in usagetype
        if "." in model_id:
            dot_pos = model_lower.index(".")
            non_vendor_parts = re.split(r"[-._:]", model_lower[dot_pos + 1:])
            non_vendor = set(p for p in non_vendor_parts if p)
        else:
            non_vendor = set(model_parts)
        if non_vendor and non_vendor.issubset(usage_tokens):
            return True

    return False


def _extract_costs_from_products(products: list, model_id: str, region: str) -> dict:
    """Extract input/output costs from a list of products for a model+region."""
    input_cost = None
    output_cost = None

    for p in products:
        entry = extract_pricing(p)

        if not _matches_model(entry, model_id, region):
            continue
        if not is_on_demand_standard(entry):
            continue

        token_type = classify_token_type(entry)
        price = entry["price_per_unit_usd"]
        if price is None:
            continue

        price_float = float(price)
        if token_type == "input" and input_cost is None:
            input_cost = price_float
        elif token_type == "output" and output_cost is None:
            output_cost = price_float

        if input_cost is not None and output_cost is not None:
            break

    return {"input_cost": input_cost, "output_cost": output_cost}


# ---------------------------------------------------------------------------
# Tier 1: Query all 3 service codes
# ---------------------------------------------------------------------------

def _query_price_list_api(model_id: str, region: str) -> dict:
    """Tier 1: Query AWS Price List API across all 3 service codes.

    Returns {"input_cost": float|None, "output_cost": float|None}.
    """
    pricing_client = boto3.client("pricing", region_name=PRICING_CLIENT_REGION)
    input_cost = None
    output_cost = None

    for sc in SERVICE_CODES:
        try:
            products = get_all_products(pricing_client, sc)
        except Exception as exc:
            logger.warning("Failed to query %s: %s", sc, exc)
            continue

        costs = _extract_costs_from_products(products, model_id, region)

        if input_cost is None and costs["input_cost"] is not None:
            input_cost = costs["input_cost"]
        if output_cost is None and costs["output_cost"] is not None:
            output_cost = costs["output_cost"]

        if input_cost is not None and output_cost is not None:
            break

    return {"input_cost": input_cost, "output_cost": output_cost}


# ---------------------------------------------------------------------------
# Tier 2: Re-query AmazonBedrockService only for missing output pricing
# ---------------------------------------------------------------------------

def _query_bedrock_service_only(model_id: str, region: str) -> dict:
    """Tier 2: Re-query only AmazonBedrockService for missing pricing.

    Some models (older Anthropic) have input pricing in AmazonBedrock
    but output pricing only in AmazonBedrockService.

    Returns {"input_cost": float|None, "output_cost": float|None}.
    """
    pricing_client = boto3.client("pricing", region_name=PRICING_CLIENT_REGION)

    try:
        products = get_all_products(pricing_client, "AmazonBedrockService")
    except Exception as exc:
        logger.warning("Failed to query AmazonBedrockService for tier 2: %s", exc)
        return {"input_cost": None, "output_cost": None}

    return _extract_costs_from_products(products, model_id, region)


# ---------------------------------------------------------------------------
# Tier 3: Scrape AWS Bedrock pricing webpage bulk JSON
# ---------------------------------------------------------------------------

def _fetch_url(url: str, timeout: int = 15) -> bytes:
    """Fetch a URL and return raw bytes. Handles gzip encoding."""
    req = urllib.request.Request(url, headers={
        "User-Agent": "BedrockBenchmark/1.0",
        "Accept-Encoding": "gzip, deflate",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read()
        if resp.headers.get("Content-Encoding") == "gzip":
            data = gzip.decompress(data)
        return data


def _parse_pricing_page(page_html: str) -> list[dict]:
    """Parse the AWS Bedrock pricing page HTML to extract model-to-hash mappings."""
    content = html_module.unescape(page_html)

    token_re = (
        r'\{priceOf!'
        r'(?P<path>[^!}]+/[^!}]+)!'
        r'(?P<hash>[A-Za-z0-9_-]+)'
        r'(?:!\*!(?P<mult>\d+))?'
        r'(?:!opt)?'
        r'\}'
    )

    token_re_unnamed = (
        r'\{priceOf!'
        r'[^!}]+/[^!}]+!'
        r'[A-Za-z0-9_-]+'
        r'(?:!\*!\d+)?'
        r'(?:!opt)?'
        r'\}'
    )

    row_re = (
        r'<td[^>]*>([^<]{2,80})</td>'
        r'\s*<td[^>]*>(' + token_re_unnamed + r')</td>'
        r'\s*<td[^>]*>(' + token_re_unnamed + r')</td>'
    )

    entries = []
    seen = set()

    for row_match in re.finditer(row_re, content):
        model_name = row_match.group(1).strip()
        input_cell = row_match.group(2)
        output_cell = row_match.group(3)

        input_m = re.search(token_re, input_cell)
        output_m = re.search(token_re, output_cell)
        if not input_m or not output_m:
            continue

        service_path = input_m.group("path")
        input_hash = input_m.group("hash")
        output_hash = output_m.group("hash")
        input_mult = int(input_m.group("mult") or "1")
        output_mult = int(output_m.group("mult") or "1")

        dedup_key = (model_name, service_path, input_hash)
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        name_lower = model_name.lower()
        if any(skip in name_lower for skip in ("long context", "batch", "priority", "flex")):
            continue

        entries.append({
            "model_name": model_name,
            "service_path": service_path,
            "input_hash": input_hash,
            "output_hash": output_hash,
            "input_mult": input_mult,
            "output_mult": output_mult,
        })

    return entries


def _normalize_for_match(s: str) -> str:
    """Normalize a model identifier for fuzzy matching."""
    s = s.lower()
    for prefix in ("anthropic.", "meta.", "amazon.", "cohere.", "ai21.",
                    "mistral.", "stability.", "deepseek.", "us.", "eu.",
                    "qwen.", "moonshot.", "openai."):
        if s.startswith(prefix):
            s = s[len(prefix):]
            break
    s = re.sub(r"-\d{8}-v\d+:\d+$", "", s)
    s = re.sub(r"-v\d+:\d+$", "", s)
    s = re.sub(r"-v\d+$", "", s)
    s = re.sub(r"[-._:]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _find_model_entry(model_id: str, entries: list[dict]) -> Optional[dict]:
    """Find the best matching entry for a model_id using fuzzy matching."""
    norm_id = _normalize_for_match(model_id)
    norm_id_nospaces = norm_id.replace(" ", "")

    best_match = None
    best_score = 0

    for entry in entries:
        norm_name = _normalize_for_match(entry["model_name"])
        norm_name_nospaces = norm_name.replace(" ", "")

        if norm_id == norm_name:
            return entry

        if norm_id_nospaces in norm_name_nospaces or norm_name_nospaces in norm_id_nospaces:
            score = len(norm_name_nospaces)
            if score > best_score:
                best_score = score
                best_match = entry
            continue

        id_tokens = set(norm_id.split())
        name_tokens = set(norm_name.split())
        overlap = len(id_tokens & name_tokens)
        if overlap >= 2 and overlap > best_score:
            best_score = overlap
            best_match = entry

    return best_match


def _fetch_bulk_json(service_path: str) -> Optional[dict]:
    """Fetch the bulk pricing JSON for a service."""
    svc = _SERVICE_PATH_MAP.get(service_path)
    if not svc:
        logger.warning("Unknown service path for bulk JSON: %s", service_path)
        return None

    url = _BULK_JSON_URL.format(svc=svc)
    try:
        data = _fetch_url(url, timeout=20)
        return json.loads(data)
    except Exception as exc:
        logger.warning("Failed to fetch bulk pricing JSON from %s: %s", url, exc)
        return None


def _scrape_webpage_pricing(model_id: str, region: str) -> dict:
    """Tier 3: Scrape AWS Bedrock pricing webpage for missing prices.

    Returns {"input_cost": float|None, "output_cost": float|None}.
    Costs are returned in per-1K-token format.
    """
    try:
        page_bytes = _fetch_url(_PRICING_PAGE_URL, timeout=20)
        page_html = page_bytes.decode("utf-8", errors="replace")
        entries = _parse_pricing_page(page_html)

        if not entries:
            logger.warning("Tier 3: No model entries parsed from pricing page")
            return {"input_cost": None, "output_cost": None}

        matched = _find_model_entry(model_id, entries)
        if not matched:
            logger.info("Tier 3: No matching model found for %s", model_id)
            return {"input_cost": None, "output_cost": None}

        logger.info(
            "Tier 3: Matched %s -> '%s' (service=%s)",
            model_id, matched["model_name"], matched["service_path"],
        )

        bulk_data = _fetch_bulk_json(matched["service_path"])
        if not bulk_data:
            return {"input_cost": None, "output_cost": None}

        region_name = _REGION_DISPLAY_NAMES.get(region)
        if not region_name:
            logger.warning("Tier 3: Unknown region code %s", region)
            return {"input_cost": None, "output_cost": None}

        region_prices = bulk_data.get("regions", {}).get(region_name, {})
        if not region_prices:
            logger.info("Tier 3: No pricing data for region %s", region_name)
            return {"input_cost": None, "output_cost": None}

        input_entry = region_prices.get(matched["input_hash"], {})
        output_entry = region_prices.get(matched["output_hash"], {})

        input_raw = float(input_entry["price"]) if input_entry.get("price") else None
        output_raw = float(output_entry["price"]) if output_entry.get("price") else None

        # Convert to per-1K-token format:
        #   {priceOf!svc!hash!*!1000} -> raw is per 1K tokens
        #   {priceOf!svc!hash}        -> raw is per 1M tokens, divide by 1000
        input_cost = None
        output_cost = None

        if input_raw is not None:
            if matched["input_mult"] >= 1000:
                input_cost = input_raw
            else:
                input_cost = input_raw / 1000.0

        if output_raw is not None:
            if matched["output_mult"] >= 1000:
                output_cost = output_raw
            else:
                output_cost = output_raw / 1000.0

        return {"input_cost": input_cost, "output_cost": output_cost}

    except Exception as exc:
        logger.warning("Tier 3 webpage pricing scrape failed: %s", exc)
        return {"input_cost": None, "output_cost": None}


# ---------------------------------------------------------------------------
# Main pricing resolver
# ---------------------------------------------------------------------------

def get_model_pricing(model_id: str, region: str) -> dict:
    """Get pricing for a model using 3-tier fallback.

    Args:
        model_id: Bedrock model ID without 'bedrock/' prefix
                  (e.g., 'anthropic.claude-sonnet-4-5-20250929-v1:0')
        region: AWS region (e.g., 'us-west-2')

    Returns:
        dict with keys: input_cost, output_cost, pricing_source
        Costs are per 1K tokens.
    """
    # Tier 1: Query Price List API (all 3 service codes)
    result = _query_price_list_api(model_id, region)

    if result["input_cost"] is not None and result["output_cost"] is not None:
        return {
            "input_cost": result["input_cost"],
            "output_cost": result["output_cost"],
            "pricing_source": "api",
        }

    # Tier 2: Re-query AmazonBedrockService for missing pricing
    if result["input_cost"] is not None or result["output_cost"] is not None:
        tier2 = _query_bedrock_service_only(model_id, region)
        if result["input_cost"] is None and tier2["input_cost"] is not None:
            result["input_cost"] = tier2["input_cost"]
        if result["output_cost"] is None and tier2["output_cost"] is not None:
            result["output_cost"] = tier2["output_cost"]

        if result["input_cost"] is not None and result["output_cost"] is not None:
            return {
                "input_cost": result["input_cost"],
                "output_cost": result["output_cost"],
                "pricing_source": "api_partial",
            }

    # Tier 3: Scrape pricing from AWS webpage bulk JSON
    tier3 = _scrape_webpage_pricing(model_id, region)
    if result["input_cost"] is None and tier3["input_cost"] is not None:
        result["input_cost"] = tier3["input_cost"]
    if result["output_cost"] is None and tier3["output_cost"] is not None:
        result["output_cost"] = tier3["output_cost"]

    if result["input_cost"] is not None and result["output_cost"] is not None:
        return {
            "input_cost": result["input_cost"],
            "output_cost": result["output_cost"],
            "pricing_source": "webpage",
        }

    return {
        "input_cost": result["input_cost"],
        "output_cost": result["output_cost"],
        "pricing_source": "unavailable",
    }


# ---------------------------------------------------------------------------
# Bulk resolution and enrichment (public API)
# ---------------------------------------------------------------------------

def _load_bedrock_entries_from_profile(path: Path) -> list[dict]:
    """Load Bedrock model entries from a JSONL profile file."""
    entries = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                try:
                    data = json.loads(line)
                    model_id = data.get("model_id", "")
                    region = data.get("region", "")
                    if model_id.startswith("bedrock/") and region:
                        entries.append({"model_id": model_id, "region": region})
                except json.JSONDecodeError:
                    continue
    except FileNotFoundError:
        logger.warning("Profile file not found: %s", path)
    return entries


def resolve_all_pricing(force: bool = False) -> dict:
    """Resolve pricing for all Bedrock models in both profile files.

    Uses local file cache with hash-based invalidation. Only re-resolves
    when models_profiles.jsonl or judge_profiles.jsonl content changes.

    Args:
        force: If True, ignore cache and re-resolve all pricing.

    Returns:
        The pricing cache dict.
    """
    if not force and is_pricing_cache_valid():
        logger.info("Pricing cache is valid, using cached pricing")
        return load_pricing_cache()

    logger.info("Resolving Bedrock model pricing...")

    cache = {
        "last_updated": None,
        "profiles_hash": get_profiles_hash(),
        "pricing": {},
    }

    # Collect unique (model_id, region) pairs from both profiles
    entries = _load_bedrock_entries_from_profile(MODELS_PROFILE_PATH)
    entries.extend(_load_bedrock_entries_from_profile(JUDGE_PROFILE_PATH))

    seen = set()
    unique_entries = []
    for e in entries:
        key = _cache_key(e["model_id"], e["region"])
        if key not in seen:
            seen.add(key)
            unique_entries.append(e)

    logger.info("Resolving pricing for %d unique Bedrock model+region combinations", len(unique_entries))

    for idx, entry in enumerate(unique_entries, 1):
        model_id = entry["model_id"]
        region = entry["region"]
        key = _cache_key(model_id, region)
        stripped_id = strip_model_id_for_pricing(model_id)

        logger.info("[%d/%d] Resolving pricing for %s @ %s", idx, len(unique_entries), stripped_id, region)

        pricing = get_model_pricing(stripped_id, region)

        cache["pricing"][key] = {
            "input_cost_per_1k": pricing["input_cost"],
            "output_cost_per_1k": pricing["output_cost"],
            "pricing_source": pricing["pricing_source"],
            "last_resolved": datetime.now(timezone.utc).isoformat(),
        }

        if pricing["pricing_source"] == "unavailable":
            logger.warning("Pricing unavailable for %s @ %s", stripped_id, region)
        else:
            logger.info(
                "  -> input: %s, output: %s (source: %s)",
                pricing["input_cost"], pricing["output_cost"], pricing["pricing_source"],
            )

    save_pricing_cache(cache)
    return cache


def enrich_model_entry(entry: dict) -> dict:
    """Overlay dynamic pricing onto a model/judge entry from JSONL.

    For Bedrock models, looks up cached pricing and replaces cost fields.
    Falls back to original JSONL values if API pricing is unavailable.
    Non-Bedrock models are returned unchanged.

    Handles both key formats:
        - Models: input_token_cost / output_token_cost
        - Judges: input_cost_per_1k / output_cost_per_1k

    Args:
        entry: A dict loaded from models_profiles.jsonl or judge_profiles.jsonl.

    Returns:
        The entry dict with pricing potentially updated.
    """
    model_id = entry.get("model_id", "")
    region = entry.get("region", "")

    if not model_id.startswith("bedrock/") or not region:
        return entry

    cache = load_pricing_cache()
    key = _cache_key(model_id, region)
    cached = cache.get("pricing", {}).get(key)

    if not cached or cached.get("pricing_source") == "unavailable":
        if cached:
            logger.warning(
                "Dynamic pricing unavailable for %s @ %s, using static JSONL values",
                model_id, region,
            )
        return entry

    input_price = cached.get("input_cost_per_1k")
    output_price = cached.get("output_cost_per_1k")

    # Update model profile keys
    if "input_token_cost" in entry and input_price is not None:
        entry["input_token_cost"] = input_price
    if "output_token_cost" in entry and output_price is not None:
        entry["output_token_cost"] = output_price

    # Update judge profile keys
    if "input_cost_per_1k" in entry and input_price is not None:
        entry["input_cost_per_1k"] = input_price
    if "output_cost_per_1k" in entry and output_price is not None:
        entry["output_cost_per_1k"] = output_price

    return entry
