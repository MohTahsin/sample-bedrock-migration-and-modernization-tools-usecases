"""Lambda handler for model and pricing discovery.

Operations:
    GET  /discovery/models          - List available Bedrock foundation models
    GET  /discovery/pricing         - Get pricing for a model+region (DynamoDB lookup)
    POST /discovery/refresh-pricing - Trigger bulk pricing refresh

Environment variables:
    PRICING_CACHE_TABLE - DynamoDB table for pricing cache
"""

import json
import logging
import os

import boto3

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from shared import pricing as pricing_service

logger = logging.getLogger()
logger.setLevel(logging.INFO)

PRICING_CACHE_TABLE = os.environ.get("PRICING_CACHE_TABLE", "")


def handler(event, context):
    """Main Lambda handler - routes based on path."""
    http_method = event.get("httpMethod", "")
    path = event.get("path", "")

    try:
        if http_method == "GET" and path.endswith("/discovery/models"):
            return _list_models(event)
        elif http_method == "GET" and path.endswith("/discovery/pricing"):
            return _get_pricing(event)
        elif http_method == "POST" and path.endswith("/discovery/refresh-pricing"):
            return _refresh_pricing(event)

        return _response(404, {"error": "Not found"})

    except Exception as exc:
        logger.exception("Unhandled error in discovery handler")
        return _response(500, {"error": str(exc)})


# ---------------------------------------------------------------------------
# Operations
# ---------------------------------------------------------------------------

def _list_models(event):
    """GET /discovery/models - List available Bedrock foundation models."""
    params = event.get("queryStringParameters") or {}
    region = params.get("region", os.environ.get("AWS_REGION", "us-east-1"))

    bedrock_client = boto3.client("bedrock", region_name=region)

    try:
        response = bedrock_client.list_foundation_models()
    except Exception as exc:
        logger.error("Failed to list foundation models in %s: %s", region, exc)
        return _response(502, {"error": f"Failed to list models: {exc}"})

    models = []
    for summary in response.get("modelSummaries", []):
        models.append({
            "model_id": summary.get("modelId", ""),
            "model_name": summary.get("modelName", ""),
            "provider_name": summary.get("providerName", ""),
            "input_modalities": summary.get("inputModalities", []),
            "output_modalities": summary.get("outputModalities", []),
            "response_streaming_supported": summary.get("responseStreamingSupported", False),
            "model_lifecycle_status": summary.get("modelLifecycle", {}).get("status", ""),
            "inference_types_supported": summary.get("inferenceTypesSupported", []),
        })

    return _response(200, {
        "models": models,
        "count": len(models),
        "region": region,
    })


def _get_pricing(event):
    """GET /discovery/pricing - Get pricing for a model+region.

    Pure DynamoDB cache lookup — no API calls at request time.
    """
    params = event.get("queryStringParameters") or {}
    model_id = params.get("model_id", "").strip()
    region = params.get("region", "").strip()

    if not model_id or not region:
        return _response(400, {"error": "model_id and region query parameters are required"})

    pricing_data = pricing_service.get_model_pricing(model_id, region)

    return _response(200, {
        "model_id": model_id,
        "region": region,
        "input_cost": pricing_data.get("input_cost"),
        "output_cost": pricing_data.get("output_cost"),
        "pricing_source": pricing_data.get("pricing_source", "unknown"),
    })


def _refresh_pricing(event):
    """POST /discovery/refresh-pricing - Trigger bulk pricing refresh.

    Fetches ALL model pricing from the Price List API and webpage,
    then batch-writes everything to DynamoDB.
    """
    logger.info("Manual pricing refresh triggered")
    summary = pricing_service.refresh_all_pricing()

    return _response(200, {
        "message": "Pricing refresh complete",
        **summary,
    })


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _response(status_code: int, body: dict) -> dict:
    """Build API Gateway proxy response."""
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,Authorization",
            "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
        },
        "body": json.dumps(body, default=str),
    }
