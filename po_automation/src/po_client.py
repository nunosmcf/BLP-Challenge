"""HTTP client for the mock ERP purchase order endpoint."""
import json
import uuid

import requests

from . import config


def create_po(requisition: dict) -> dict:
    """POST a requisition to the mock ERP and return the response body.

    The requisition dict must have:
      supplier_id, currency, total_original, requested_delivery_date, items_json

    Raises requests.HTTPError on 4xx/5xx that are not 422.
    Returns {"error": ..., "problems": ...} on 422 (ERP validation failure).
    """
    items_raw = requisition.get("items_json") or "[]"
    try:
        items = json.loads(items_raw)
    except (json.JSONDecodeError, TypeError):
        items = []

    line_items = []
    for item in items:
        line_items.append({
            "item_name":  item.get("item_name", "unspecified"),
            "quantity":   item.get("quantity", 1),
            "unit_price": item.get("unit_price", 0),
            "unit":       item.get("unit", "pcs"),
            "item_code":  item.get("item_code"),
        })

    payload = {
        "supplier_id":              requisition["supplier_id"],
        "currency":                 requisition["currency"],
        "total":                    requisition["total_original"],
        "requested_delivery_date":  requisition.get("requested_delivery_date"),
        "cost_centre":              requisition.get("cost_center_code"),
        "gl_account":               requisition.get("gl_account_code"),
        "line_items":               line_items,
        "requisition_reference":    requisition["id"],
    }
    # Strip None values from optional fields
    payload = {k: v for k, v in payload.items() if v is not None}

    idempotency_key = str(uuid.uuid5(uuid.NAMESPACE_URL, requisition["id"]))
    headers = {
        "Content-Type":    "application/json",
        "Idempotency-Key": idempotency_key,
    }

    resp = requests.post(config.PO_API_URL, json=payload, headers=headers, timeout=10)

    if resp.status_code in (200, 201):
        return resp.json()

    if resp.status_code == 422:
        return resp.json()  # {"error": ..., "problems": [...]}

    resp.raise_for_status()
    return {}
