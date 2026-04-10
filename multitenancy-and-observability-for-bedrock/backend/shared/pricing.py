"""Bedrock model pricing with 3-tier fallback and DynamoDB caching.

Ported from 360-eval/src/bedrock_pricing.py. Uses the exact same extraction
pipeline (Price List API + webpage scraping) but stores results in DynamoDB
instead of a local file cache.

Flow:
    - refresh_all_pricing() discovers ALL Bedrock models via
      list_foundation_models(), fetches ALL pricing from the Price List API
      with webpage fallback, and batch-writes everything to DynamoDB.
      Called at deploy time (seed script), weekly (EventBridge + Lambda),
      or on-demand (POST /discovery/refresh-pricing).
    - get_model_pricing() checks DynamoDB cache first, then falls back to
      the 3-tier fetch for cache misses.

Environment variables:
    PRICING_CACHE_TABLE - DynamoDB table for pricing cache
"""

import gzip
import html as html_module
import json
import logging
import os
import re
import time
import urllib.request
from decimal import Decimal
from typing import Optional

import boto3

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SERVICE_CODES = [
    "AmazonBedrock",
    "AmazonBedrockService",
    "AmazonBedrockFoundationModels",
]
PRICING_CLIENT_REGION = "us-east-1"
CACHE_TTL_SECONDS = 604800  # 7 days

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
    """Build cache key from model_id and region.

    Strips bedrock/ but keeps cross-region prefix for uniqueness.
    """
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
    price_unit = ""
    for offer in terms.get("OnDemand", {}).values():
        for dim in offer.get("priceDimensions", {}).values():
            price_per_unit = dim.get("pricePerUnit", {}).get("USD")
            price_unit = dim.get("unit", "")
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
        "price_unit": price_unit,
    }


def _normalize_to_per_1m(price: float, unit: str) -> float:
    """Convert a price to per-1M-token format based on the unit string.

    Args:
        price: The raw price value.
        unit: The unit string from the API (e.g., "1K tokens", "1M tokens").

    Returns:
        Price normalized to per-1M tokens.
    """
    unit_lower = unit.lower()
    if "1k" in unit_lower or "thousand" in unit_lower:
        return round(price * 1000, 2)
    if "1m" in unit_lower or "million" in unit_lower or not unit:
        return round(price, 2)
    logger.warning("Unrecognized pricing unit '%s', assuming per-1M tokens", unit)
    return round(price, 2)


def is_on_demand_standard(entry: dict) -> bool:
    """Filter to only on-demand, non-reserved, non-batch, non-cache entries."""
    usagetype = entry["usagetype"].lower()
    feature = entry["feature"].lower()
    feature_type = entry["feature_type"].lower()

    for skip in ("reserved", "batch", "cache", "long-context", "latency-optimized",
                  "-flex", "-priority", "-standard"):
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

        price_float = _normalize_to_per_1m(float(price), entry.get("price_unit", ""))
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

def _fetch_all_products_parallel() -> list:
    """Fetch all products from all 3 service codes in parallel.

    Returns a combined list of all product entries.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    pricing_client = boto3.client("pricing", region_name=PRICING_CLIENT_REGION)
    all_products = []

    def fetch_service(sc):
        try:
            products = get_all_products(pricing_client, sc)
            logger.info("Fetched %d products from %s", len(products), sc)
            return products
        except Exception as exc:
            logger.warning("Failed to query %s: %s", sc, exc)
            return []

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(fetch_service, sc): sc for sc in SERVICE_CODES}
        for future in as_completed(futures):
            all_products.extend(future.result())

    logger.info("Total products fetched: %d", len(all_products))
    return all_products


def _resolve_bulk_from_products(
    products: list, models: list[tuple[str, str]]
) -> dict[str, dict]:
    """Match all (model_id, region) pairs against a pre-fetched product list.

    Args:
        products: Combined product list from all service codes.
        models: List of (stripped_model_id, region) tuples.

    Returns:
        Dict keyed by "region#model_id" with {input_cost, output_cost} values.
    """
    # Pre-extract all pricing entries once
    entries = []
    for p in products:
        entry = extract_pricing(p)
        if not is_on_demand_standard(entry):
            continue
        token_type = classify_token_type(entry)
        if token_type == "unknown":
            continue
        price = entry["price_per_unit_usd"]
        if price is None:
            continue
        entry["_token_type"] = token_type
        entry["_price_float"] = _normalize_to_per_1m(float(price), entry.get("price_unit", ""))
        entries.append(entry)

    logger.info("Pre-filtered to %d on-demand pricing entries", len(entries))

    results = {}
    for model_id, region in models:
        key = f"{region}#{model_id}"
        input_cost = None
        output_cost = None

        for entry in entries:
            if not _matches_model(entry, model_id, region):
                continue

            if entry["_token_type"] == "input" and input_cost is None:
                input_cost = entry["_price_float"]
            elif entry["_token_type"] == "output" and output_cost is None:
                output_cost = entry["_price_float"]

            if input_cost is not None and output_cost is not None:
                break

        results[key] = {"input_cost": input_cost, "output_cost": output_cost}

    return results


def _query_price_list_api(model_id: str, region: str) -> dict:
    """Tier 1: Query AWS Price List API across all 3 service codes.

    Returns {"input_cost": float|None, "output_cost": float|None}.
    """
    products = _fetch_all_products_parallel()
    return _extract_costs_from_products(products, model_id, region)


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

        # Substring match: require both sides to be at least 6 chars to avoid
        # false positives like "text" matching "titan embed text"
        if len(norm_id_nospaces) >= 6 and len(norm_name_nospaces) >= 6:
            if norm_id_nospaces in norm_name_nospaces or norm_name_nospaces in norm_id_nospaces:
                score = len(norm_name_nospaces)
                if score > best_score:
                    best_score = score
                    best_match = entry
                continue

        id_tokens = set(norm_id.split())
        name_tokens = set(norm_name.split())
        # Exclude pure numeric tokens from matching (e.g., "1", "2") to avoid
        # false positives like "pegasus 1 2" matching "claude 2 1"
        id_meaningful = {t for t in id_tokens if not t.isdigit()}
        name_meaningful = {t for t in name_tokens if not t.isdigit()}
        overlap = len(id_meaningful & name_meaningful)
        # Require at least 2 meaningful token matches AND >50% overlap
        min_tokens = min(len(id_meaningful), len(name_meaningful))
        if overlap >= 2 and min_tokens > 0 and overlap / min_tokens > 0.5 and overlap > best_score:
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


def _resolve_single_from_webpage(
    model_id: str, region: str, entries: list[dict], bulk_cache: dict
) -> dict:
    """Resolve pricing for a single model from pre-fetched webpage data.

    Args:
        model_id: Stripped model ID.
        region: AWS region.
        entries: Parsed pricing page entries (from _parse_pricing_page).
        bulk_cache: Dict to cache bulk JSON data by service_path (shared across calls).

    Returns {"input_cost": float|None, "output_cost": float|None}.
    """
    if not entries:
        return {"input_cost": None, "output_cost": None}

    matched = _find_model_entry(model_id, entries)
    if not matched:
        logger.info("Tier 3: No matching model found for %s", model_id)
        return {"input_cost": None, "output_cost": None}

    logger.info(
        "Tier 3: Matched %s -> '%s' (service=%s)",
        model_id, matched["model_name"], matched["service_path"],
    )

    # Use cached bulk JSON or fetch it
    sp = matched["service_path"]
    if sp not in bulk_cache:
        bulk_cache[sp] = _fetch_bulk_json(sp)
    bulk_data = bulk_cache[sp]

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

    # Convert to per-1M-token format:
    #   {priceOf!svc!hash!*!1000} -> raw is per 1K tokens, multiply by 1000
    #   {priceOf!svc!hash}        -> raw is per 1M tokens, keep as-is
    input_cost = None
    output_cost = None

    if input_raw is not None:
        input_cost = round(input_raw * 1000 if matched["input_mult"] >= 1000 else input_raw, 2)

    if output_raw is not None:
        output_cost = round(output_raw * 1000 if matched["output_mult"] >= 1000 else output_raw, 2)

    return {"input_cost": input_cost, "output_cost": output_cost}


def _scrape_webpage_pricing(model_id: str, region: str) -> dict:
    """Tier 3: Scrape AWS Bedrock pricing webpage for a single model.

    Returns {"input_cost": float|None, "output_cost": float|None}.
    Costs are returned in per-1M-token format.
    """
    try:
        page_bytes = _fetch_url(_PRICING_PAGE_URL, timeout=20)
        page_html = page_bytes.decode("utf-8", errors="replace")
        entries = _parse_pricing_page(page_html)
        bulk_cache = {}
        return _resolve_single_from_webpage(model_id, region, entries, bulk_cache)
    except Exception as exc:
        logger.warning("Tier 3 webpage pricing scrape failed: %s", exc)
        return {"input_cost": None, "output_cost": None}


def _scrape_webpage_pricing_bulk(models: list[tuple[str, str]]) -> dict[str, dict]:
    """Tier 3 bulk: Scrape webpage once and resolve all models.

    Fetches the pricing page HTML once, parses it, then resolves all models
    sharing the cached HTML and bulk JSON data.

    Args:
        models: List of (stripped_model_id, region) tuples.

    Returns:
        Dict keyed by "region#model_id" with {input_cost, output_cost} values.
    """
    results = {}

    try:
        page_bytes = _fetch_url(_PRICING_PAGE_URL, timeout=20)
        page_html = page_bytes.decode("utf-8", errors="replace")
        entries = _parse_pricing_page(page_html)

        if not entries:
            logger.warning("Tier 3 bulk: No model entries parsed from pricing page")
            return {f"{reg}#{mid}": {"input_cost": None, "output_cost": None} for mid, reg in models}

        logger.info("Tier 3 bulk: Parsed %d entries from pricing page", len(entries))

        # Shared cache for bulk JSON files (avoids re-fetching per service_path)
        bulk_cache = {}

        for model_id, region in models:
            key = f"{region}#{model_id}"
            results[key] = _resolve_single_from_webpage(model_id, region, entries, bulk_cache)

    except Exception as exc:
        logger.warning("Tier 3 bulk webpage scrape failed: %s", exc)
        for model_id, region in models:
            key = f"{region}#{model_id}"
            if key not in results:
                results[key] = {"input_cost": None, "output_cost": None}

    return results


# ---------------------------------------------------------------------------
# Single-model pricing resolver (3-tier fallback)
# ---------------------------------------------------------------------------

def _get_model_pricing_from_api(model_id: str, region: str) -> dict:
    """Get pricing for a model using 3-tier fallback.

    Args:
        model_id: Bedrock model ID without 'bedrock/' prefix
                  (e.g., 'anthropic.claude-sonnet-4-5-20250929-v1:0')
        region: AWS region (e.g., 'us-west-2')

    Returns:
        dict with keys: input_cost, output_cost, pricing_source
        Costs are per 1M tokens.
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
# DynamoDB pricing cache
# ---------------------------------------------------------------------------

def _get_pricing_table():
    """Get DynamoDB Table resource for pricing cache."""
    table_name = os.environ.get("PRICING_CACHE_TABLE", "")
    if not table_name:
        raise EnvironmentError("PRICING_CACHE_TABLE environment variable not set")
    dynamodb = boto3.resource("dynamodb")
    return dynamodb.Table(table_name)


def cache_pricing(table, cache_key: str, pricing_data: dict) -> None:
    """Write pricing data to DynamoDB with 7-day TTL."""
    now = time.time()
    item = {
        "region#model_id": cache_key,
        "model_id": pricing_data.get("model_id", cache_key.split("#", 1)[-1]),
        "region": pricing_data.get("region", cache_key.split("#", 1)[0]),
        "input_cost": Decimal(str(pricing_data["input_cost"])) if pricing_data.get("input_cost") is not None else Decimal("0"),
        "output_cost": Decimal(str(pricing_data["output_cost"])) if pricing_data.get("output_cost") is not None else Decimal("0"),
        "pricing_source": pricing_data.get("pricing_source", "unknown"),
        "cached_at": Decimal(str(now)),
        "ttl": int(now) + CACHE_TTL_SECONDS,
    }
    table.put_item(Item=item)


def get_cached_pricing(table, cache_key: str) -> Optional[dict]:
    """Read pricing from DynamoDB cache. Returns None if missing or expired."""
    try:
        response = table.get_item(Key={"region#model_id": cache_key})
    except Exception as exc:
        logger.warning("Failed to read pricing cache for %s: %s", cache_key, exc)
        return None

    item = response.get("Item")
    if not item:
        return None

    ttl = int(item.get("ttl", 0))
    if ttl > 0 and ttl < int(time.time()):
        return None

    return {
        "model_id": item.get("model_id", ""),
        "region": item.get("region", ""),
        "input_cost": float(item.get("input_cost", 0)),
        "output_cost": float(item.get("output_cost", 0)),
        "pricing_source": item.get("pricing_source", "unknown"),
        "cached_at": float(item.get("cached_at", 0)),
        "ttl": ttl,
    }


# ---------------------------------------------------------------------------
# Model discovery
# ---------------------------------------------------------------------------

def _discover_all_models() -> list[str]:
    """Discover all Bedrock model IDs via list_foundation_models().

    Returns a deduplicated list of model IDs (with vendor prefix,
    e.g., 'anthropic.claude-sonnet-4-5-20250929-v1:0').
    """
    try:
        client = boto3.client("bedrock", region_name="us-east-1")
        resp = client.list_foundation_models()

        model_ids = set()
        for m in resp.get("modelSummaries", []):
            model_id = m.get("modelId", "")
            if model_id:
                # Skip provisioned-only variants
                if re.search(r":\d+k$", model_id) or re.search(r":mm$", model_id):
                    continue
                model_ids.add(model_id)

        logger.info("Discovered %d unique Bedrock model IDs", len(model_ids))
        return sorted(model_ids)

    except Exception as exc:
        logger.error("Failed to discover Bedrock models: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Bulk refresh: fetch pricing, cache everything to DynamoDB
# ---------------------------------------------------------------------------

def refresh_all_pricing() -> dict:
    """Fetch ALL pricing from API + webpage and cache to DynamoDB.

    1. Discover models via list_foundation_models()
    2. Tier 1: Fetch all products from Price List API, match all models
    3. Tier 3: Webpage fallback for models still missing pricing
    4. Batch-write everything to DynamoDB with 7-day TTL

    Called at deploy time (seed script), weekly (EventBridge + Lambda),
    or on-demand (POST /discovery/refresh-pricing).

    Returns:
        Summary dict with counts and status.
    """
    logger.info("=== Starting bulk pricing refresh ===")

    # --- Step 1: Discover all Bedrock models ---
    model_ids = _discover_all_models()
    if not model_ids:
        return {"status": "error", "error": "No models discovered", "total": 0, "api_resolved": 0, "written": 0}

    # --- Step 2: Tier 1 - Fetch all products and resolve pricing ---
    try:
        all_products = _fetch_all_products_parallel()
    except Exception as exc:
        logger.error("Bulk API fetch failed: %s", exc)
        return {"status": "error", "error": str(exc), "total": 0, "api_resolved": 0, "written": 0}

    # Extract regions that actually have pricing data
    product_regions = set()
    for p in all_products:
        rc = p.get("product", {}).get("attributes", {}).get("regionCode", "")
        if rc:
            product_regions.add(rc)

    logger.info("Found pricing data in %d regions", len(product_regions))

    # Build (model_id, region) pairs — strip for pricing lookup
    model_region_pairs = []
    key_map = {}  # maps "region#stripped_id" -> cache_key
    for model_id in model_ids:
        stripped_id = strip_model_id_for_pricing(model_id)
        for region in product_regions:
            bulk_key = f"{region}#{stripped_id}"
            cache_k = f"{region}#{model_id}"
            model_region_pairs.append((stripped_id, region))
            key_map[bulk_key] = cache_k

    logger.info("Resolving pricing for %d model+region combinations", len(model_region_pairs))

    # Tier 1: Match all models against products
    api_results = _resolve_bulk_from_products(all_products, model_region_pairs)

    api_resolved = sum(
        1 for v in api_results.values()
        if v["input_cost"] is not None and v["output_cost"] is not None
    )
    logger.info("Tier 1: %d/%d fully resolved from API", api_resolved, len(model_region_pairs))

    # --- Step 3: Tier 3 - Webpage fallback for missing models ---
    missing = [
        (mid, reg) for mid, reg in model_region_pairs
        if api_results.get(f"{reg}#{mid}", {}).get("input_cost") is None
        or api_results.get(f"{reg}#{mid}", {}).get("output_cost") is None
    ]

    if missing:
        logger.info("Tier 3: Scraping webpage pricing for %d remaining model+region pairs...", len(missing))
        tier3_results = _scrape_webpage_pricing_bulk(missing)

        for stripped_id, region in missing:
            bulk_key = f"{region}#{stripped_id}"
            api_r = api_results.get(bulk_key, {"input_cost": None, "output_cost": None})
            tier3 = tier3_results.get(bulk_key, {"input_cost": None, "output_cost": None})

            if api_r["input_cost"] is None and tier3["input_cost"] is not None:
                api_r["input_cost"] = tier3["input_cost"]
            if api_r["output_cost"] is None and tier3["output_cost"] is not None:
                api_r["output_cost"] = tier3["output_cost"]
            api_results[bulk_key] = api_r

    total_resolved = sum(
        1 for v in api_results.values()
        if v["input_cost"] is not None and v["output_cost"] is not None
    )
    logger.info("After webpage merge: %d/%d fully resolved", total_resolved, len(model_region_pairs))

    # --- Step 4: Batch-write to DynamoDB ---
    written = 0
    table_name = os.environ.get("PRICING_CACHE_TABLE", "")
    if table_name:
        try:
            table = _get_pricing_table()
            now = time.time()
            with table.batch_writer() as batch:
                for bulk_key, costs in api_results.items():
                    if costs["input_cost"] is None and costs["output_cost"] is None:
                        continue

                    cache_k = key_map.get(bulk_key, bulk_key)
                    region_part, model_id_part = cache_k.split("#", 1)

                    batch.put_item(Item={
                        "region#model_id": cache_k,
                        "model_id": model_id_part,
                        "region": region_part,
                        "input_cost": Decimal(str(costs["input_cost"])) if costs["input_cost"] is not None else Decimal("0"),
                        "output_cost": Decimal(str(costs["output_cost"])) if costs["output_cost"] is not None else Decimal("0"),
                        "pricing_source": "api",
                        "cached_at": Decimal(str(now)),
                        "ttl": int(now) + CACHE_TTL_SECONDS,
                    })
                    written += 1

            logger.info("Batch-cached %d pricing entries to DynamoDB", written)
        except Exception as exc:
            logger.error("Failed to batch-cache pricing: %s", exc)
            return {
                "status": "partial_error",
                "error": f"DynamoDB write failed: {exc}",
                "total": len(api_results),
                "api_resolved": api_resolved,
                "written": 0,
            }

    summary = {
        "status": "success",
        "total": len(api_results),
        "api_resolved": total_resolved,
        "written": written,
    }
    logger.info("=== Pricing refresh complete: %s ===", summary)
    return summary


# ---------------------------------------------------------------------------
# Main entry point: DynamoDB lookup with API fallback
# ---------------------------------------------------------------------------

def get_model_pricing(model_id: str, region: str) -> dict:
    """Get pricing for a model. Checks DynamoDB cache first, falls back to API.

    Args:
        model_id: Bedrock model ID (e.g., 'anthropic.claude-sonnet-4-5-20250929-v1:0')
        region: AWS region (e.g., 'us-west-2')

    Returns:
        dict with keys: input_cost, output_cost, pricing_source
        Costs are per 1M tokens.
    """
    cache_key = f"{region}#{model_id}"

    # Try DynamoDB cache first
    table_name = os.environ.get("PRICING_CACHE_TABLE", "")
    if table_name:
        try:
            table = _get_pricing_table()
            cached = get_cached_pricing(table, cache_key)
            if cached:
                return {
                    "input_cost": cached["input_cost"],
                    "output_cost": cached["output_cost"],
                    "pricing_source": cached.get("pricing_source", "cached"),
                }
        except Exception as exc:
            logger.warning("Cache lookup failed for %s: %s", cache_key, exc)

    # Cache miss — run 3-tier fallback
    stripped_id = strip_model_id_for_pricing(model_id)
    result = _get_model_pricing_from_api(stripped_id, region)

    # Cache the result for future lookups
    if table_name and result["pricing_source"] != "unavailable":
        try:
            table = _get_pricing_table()
            cache_pricing(table, cache_key, {
                "model_id": model_id,
                "region": region,
                "input_cost": result["input_cost"],
                "output_cost": result["output_cost"],
                "pricing_source": result["pricing_source"],
            })
        except Exception as exc:
            logger.warning("Failed to cache pricing for %s: %s", cache_key, exc)

    return result
