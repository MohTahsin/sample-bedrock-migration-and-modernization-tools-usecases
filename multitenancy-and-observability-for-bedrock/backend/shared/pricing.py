"""Bedrock model pricing with bulk ingestion and DynamoDB cache.

Architecture:
    - refresh_all_pricing() discovers ALL Bedrock models via
      list_foundation_models(), fetches ALL pricing from the Price List API,
      fuzzy-matches each model, and batch-writes everything to DynamoDB.
      Called at deploy time (seed script), weekly (EventBridge + Lambda),
      or on-demand (POST /discovery/refresh-pricing).
    - get_model_pricing() is a pure DynamoDB lookup — no API calls at
      request time.

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
        "model_id": attrs.get("modelId", "") or attrs.get("model", ""),
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
    """Convert a price to per-1M-token format based on the unit string."""
    unit_lower = unit.lower()
    if "1k" in unit_lower or "thousand" in unit_lower:
        return round(price * 1000, 2)
    if "1m" in unit_lower or "million" in unit_lower or not unit:
        return round(price, 2)
    logger.warning("Unrecognized pricing unit '%s', assuming per-1M tokens", unit)
    return round(price, 2)


def is_on_demand_standard(entry: dict) -> bool:
    """Filter to only default on-demand inference entries.

    Excludes: reserved, batch, cache, long-context, latency-optimized,
    flex/priority/standard tiers, provisioned throughput, model customization,
    and training entries.
    """
    usagetype = entry["usagetype"].lower()
    feature = entry["feature"].lower()
    feature_type = entry["feature_type"].lower()
    inference_type = entry.get("inference_type", "").lower()

    all_fields = usagetype + " " + feature + " " + feature_type + " " + inference_type

    for skip in ("reserved", "batch", "cache", "long-context", "latency-optimized",
                  "flex", "priority", "standard", "provisioned", "customization",
                  "custom-model", "training"):
        if skip in all_fields:
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
    model_parts = re.split(r"[-._:]", model_lower)
    model_parts = [p for p in model_parts if p]
    if entry_usagetype and len(model_parts) > 1:
        usage_tokens = set(re.split(r"[-._:]", entry_usagetype)) - {""}
        if "." in model_id:
            dot_pos = model_lower.index(".")
            non_vendor_parts = re.split(r"[-._:]", model_lower[dot_pos + 1:])
            non_vendor = set(p for p in non_vendor_parts if p)
        else:
            non_vendor = set(model_parts)
        if non_vendor and non_vendor.issubset(usage_tokens):
            return True

    return False


# ---------------------------------------------------------------------------
# Tier 1: Fetch all products and resolve pricing via fuzzy matching
# ---------------------------------------------------------------------------

def _fetch_all_products_parallel() -> list:
    """Fetch all products from all 3 service codes in parallel."""
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

    Uses fuzzy matching via _matches_model() — no hardcoded model lists needed.

    Args:
        products: Combined product list from all service codes.
        models: List of (model_id, region) tuples.

    Returns:
        Dict keyed by "region#model_id" with {input_cost, output_cost} values.
    """
    # Pre-extract and filter all pricing entries once
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


# ---------------------------------------------------------------------------
# Discover all Bedrock models across regions
# ---------------------------------------------------------------------------

def _discover_all_models() -> list[tuple[str, str]]:
    """Discover all Bedrock model IDs across all regions.

    Calls list_foundation_models() in each region to get the full set of
    (model_id, region) pairs. No hardcoded model lists.

    Returns:
        List of (model_id, region) tuples.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    regions = list(_REGION_DISPLAY_NAMES.keys())
    all_models: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def list_models_in_region(region: str) -> list[tuple[str, str]]:
        try:
            client = boto3.client("bedrock", region_name=region)
            resp = client.list_foundation_models()
            pairs = []
            for m in resp.get("modelSummaries", []):
                model_id = m.get("modelId", "")
                if model_id:
                    pairs.append((model_id, region))
            return pairs
        except Exception as exc:
            logger.warning("Failed to list models in %s: %s", region, exc)
            return []

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(list_models_in_region, r): r for r in regions}
        for future in as_completed(futures):
            for pair in future.result():
                if pair not in seen:
                    seen.add(pair)
                    all_models.append(pair)

    logger.info("Discovered %d unique model+region combinations across %d regions",
                len(all_models), len(regions))
    return all_models


# ---------------------------------------------------------------------------
# Tier 3: Scrape AWS Bedrock pricing webpage bulk JSON
# ---------------------------------------------------------------------------

def _fetch_url(url: str, timeout: int = 15) -> bytes:
    """Fetch a URL and return raw bytes. Handles gzip encoding."""
    req = urllib.request.Request(url, headers={
        "User-Agent": "ISVBedrockObservability/1.0",
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
    """Normalize a model identifier for fuzzy matching.

    Strips vendor prefix (everything before first dot), version suffixes,
    and normalizes separators.
    """
    s = s.lower()
    # Strip vendor prefix (everything before first dot, e.g. "anthropic.", "us.")
    if "." in s:
        s = s[s.index(".") + 1:]
    # Remove version suffixes like -20240307-v1:0, -v1:0
    s = re.sub(r"-\d{8}-v\d+:\d+$", "", s)
    s = re.sub(r"-v\d+:\d+$", "", s)
    s = re.sub(r"-v\d+$", "", s)
    # Normalize separators
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

        if len(norm_id_nospaces) >= 6 and len(norm_name_nospaces) >= 6:
            if norm_id_nospaces in norm_name_nospaces or norm_name_nospaces in norm_id_nospaces:
                score = len(norm_name_nospaces)
                if score > best_score:
                    best_score = score
                    best_match = entry
                continue

        id_tokens = set(norm_id.split())
        name_tokens = set(norm_name.split())
        id_meaningful = {t for t in id_tokens if not t.isdigit()}
        name_meaningful = {t for t in name_tokens if not t.isdigit()}
        overlap = len(id_meaningful & name_meaningful)
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
    """Resolve pricing for a single model from pre-fetched webpage data."""
    if not entries:
        return {"input_cost": None, "output_cost": None}

    matched = _find_model_entry(model_id, entries)
    if not matched:
        return {"input_cost": None, "output_cost": None}

    logger.info(
        "Tier 3: Matched %s -> '%s' (service=%s)",
        model_id, matched["model_name"], matched["service_path"],
    )

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
        return {"input_cost": None, "output_cost": None}

    input_entry = region_prices.get(matched["input_hash"], {})
    output_entry = region_prices.get(matched["output_hash"], {})

    input_raw = float(input_entry["price"]) if input_entry.get("price") else None
    output_raw = float(output_entry["price"]) if output_entry.get("price") else None

    input_cost = None
    output_cost = None

    if input_raw is not None:
        input_cost = round(input_raw * 1000 if matched["input_mult"] >= 1000 else input_raw, 2)
    if output_raw is not None:
        output_cost = round(output_raw * 1000 if matched["output_mult"] >= 1000 else output_raw, 2)

    return {"input_cost": input_cost, "output_cost": output_cost}


def _scrape_webpage_pricing_bulk(
    models_missing: list[tuple[str, str]]
) -> dict[str, dict]:
    """Tier 3 bulk: Scrape webpage once and resolve all missing models."""
    results = {}

    try:
        page_bytes = _fetch_url(_PRICING_PAGE_URL, timeout=20)
        page_html = page_bytes.decode("utf-8", errors="replace")
        entries = _parse_pricing_page(page_html)

        if not entries:
            logger.warning("Tier 3 bulk: No model entries parsed from pricing page")
            return {f"{reg}#{mid}": {"input_cost": None, "output_cost": None}
                    for mid, reg in models_missing}

        logger.info("Tier 3 bulk: Parsed %d entries from pricing page", len(entries))

        bulk_cache: dict = {}
        for model_id, region in models_missing:
            key = f"{region}#{model_id}"
            results[key] = _resolve_single_from_webpage(model_id, region, entries, bulk_cache)

    except Exception as exc:
        logger.warning("Tier 3 bulk webpage scrape failed: %s", exc)
        for model_id, region in models_missing:
            key = f"{region}#{model_id}"
            if key not in results:
                results[key] = {"input_cost": None, "output_cost": None}

    return results


# ---------------------------------------------------------------------------
# Bulk refresh: discover models, fetch pricing, cache everything
# ---------------------------------------------------------------------------

def refresh_all_pricing() -> dict:
    """Discover ALL Bedrock models, fetch ALL pricing, cache to DynamoDB.

    Called at deploy time (seed script), weekly (EventBridge + Lambda),
    or on-demand (POST /discovery/refresh-pricing).

    Flow:
        1. Discover all model IDs across all regions via list_foundation_models()
        2. Fetch all products from all 3 Price List API service codes in parallel
        3. Fuzzy-match each model against the products to extract pricing
        4. Bulk-scrape the webpage for models still missing pricing
        5. Batch-write everything to DynamoDB with 7-day TTL

    Returns:
        Summary dict with counts and status.
    """
    logger.info("=== Starting bulk pricing refresh ===")

    # --- Step 1: Discover all models ---
    model_region_pairs = _discover_all_models()
    if not model_region_pairs:
        return {"status": "error", "error": "No models discovered", "total": 0}

    # --- Step 2+3: Fetch all products, fuzzy-match all models ---
    logger.info("Tier 1: Fetching all products from Price List API (parallel)...")
    try:
        all_products = _fetch_all_products_parallel()
        api_results = _resolve_bulk_from_products(all_products, model_region_pairs)
    except Exception as exc:
        logger.error("Bulk API fetch failed: %s", exc)
        return {"status": "error", "error": str(exc), "total": len(model_region_pairs)}

    api_resolved = sum(
        1 for v in api_results.values()
        if v["input_cost"] is not None and v["output_cost"] is not None
    )
    logger.info("Tier 1: Resolved %d / %d from API", api_resolved, len(model_region_pairs))

    # --- Step 4: Webpage bulk scrape for incomplete entries ---
    missing = [
        (mid, reg) for mid, reg in model_region_pairs
        if api_results.get(f"{reg}#{mid}", {}).get("input_cost") is None
        or api_results.get(f"{reg}#{mid}", {}).get("output_cost") is None
    ]

    webpage_filled = 0
    if missing:
        logger.info("Tier 3: Scraping webpage for %d models with incomplete pricing...", len(missing))
        tier3_results = _scrape_webpage_pricing_bulk(missing)

        for model_id, region in missing:
            key = f"{region}#{model_id}"
            api_r = api_results.get(key, {"input_cost": None, "output_cost": None})
            tier3 = tier3_results.get(key, {"input_cost": None, "output_cost": None})

            filled = False
            if api_r["input_cost"] is None and tier3["input_cost"] is not None:
                api_r["input_cost"] = tier3["input_cost"]
                filled = True
            if api_r["output_cost"] is None and tier3["output_cost"] is not None:
                api_r["output_cost"] = tier3["output_cost"]
                filled = True
            if filled:
                webpage_filled += 1
            api_results[key] = api_r

    # --- Step 5: Batch-write to DynamoDB ---
    missing_set = {f"{reg}#{mid}" for mid, reg in missing}
    written = 0
    table_name = os.environ.get("PRICING_CACHE_TABLE", "")
    if table_name:
        try:
            table = _get_pricing_table()
            now = time.time()
            with table.batch_writer() as batch:
                for cache_key, costs in api_results.items():
                    if costs["input_cost"] is None and costs["output_cost"] is None:
                        continue
                    region_part, model_part = cache_key.split("#", 1)
                    source = "webpage" if cache_key in missing_set else "api"

                    batch.put_item(Item={
                        "region#model_id": cache_key,
                        "model_id": model_part,
                        "region": region_part,
                        "input_cost": Decimal(str(costs["input_cost"])) if costs["input_cost"] is not None else Decimal("0"),
                        "output_cost": Decimal(str(costs["output_cost"])) if costs["output_cost"] is not None else Decimal("0"),
                        "pricing_source": source,
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
                "total": len(model_region_pairs),
                "api_resolved": api_resolved,
                "webpage_filled": webpage_filled,
                "written": 0,
            }

    summary = {
        "status": "success",
        "total": len(model_region_pairs),
        "api_resolved": api_resolved,
        "webpage_filled": webpage_filled,
        "written": written,
        "still_missing": len(model_region_pairs) - written,
    }
    logger.info("=== Pricing refresh complete: %s ===", summary)
    return summary


# ---------------------------------------------------------------------------
# Main entry point: pure DynamoDB lookup
# ---------------------------------------------------------------------------

def get_model_pricing(model_id: str, region: str) -> dict:
    """Look up pricing for a model from DynamoDB cache.

    Pure cache read — no API calls. If pricing is not cached, returns
    pricing_source="unavailable". Use refresh_all_pricing() to populate.

    Returns:
        dict with keys: input_cost, output_cost, pricing_source
    """
    cache_key = f"{region}#{model_id}"

    table_name = os.environ.get("PRICING_CACHE_TABLE", "")
    if not table_name:
        return {"input_cost": None, "output_cost": None, "pricing_source": "unavailable"}

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

    return {"input_cost": None, "output_cost": None, "pricing_source": "unavailable"}


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
