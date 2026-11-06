"""Send email + PDF text to Ollama and extract a structured purchase request.

Requires Ollama running locally with llama3.2 pulled:
  ollama serve
  ollama pull llama3.2

OLLAMA_MODEL can be changed in config.py.
"""
import json
import re
from datetime import date

import ollama

from . import config, master_data


SYSTEM_PROMPT = """You are a procurement intake assistant. Your job is to read a purchase
request email and any attached supplier quote, then extract structured data for the
ERP system. Be precise. Return only valid JSON with no prose or markdown fences."""


def _build_user_prompt(
    sender_email: str,
    subject: str,
    body: str,
    quote_texts: list[str],
    today: str,
) -> str:
    quotes_block = ""
    if quote_texts:
        quotes_block = "\n\n## Attached Quote(s)\n" + "\n\n---\n".join(quote_texts)

    return f"""Today's date: {today}

## Master Data (use these for entity resolution)

### Suppliers
{master_data.all_suppliers_summary()}

### Cost Centers
{master_data.all_cost_centers_summary()}

### GL Accounts
{master_data.all_gl_accounts_summary()}

### Employees
{master_data.all_employees_summary()}

## Email

From: {sender_email}
Subject: {subject}

{body}
{quotes_block}

## Task

Extract the purchase request and return ONLY this JSON object (no markdown, no prose):

{{
  "requester_email": "<email address of the person making the request>",
  "supplier_id": "<SUP-XXX from master data, or null if not identified>",
  "supplier_name": "<name as it appears in the email or quote>",
  "cost_center_code": "<CC-XXXX from master data, or null>",
  "gl_account_code": "<4-digit code from master data, best guess based on item type, or null>",
  "currency": "<CHF|EUR|USD|GBP — from the quote or email>",
  "total_amount": <number, total order value in the stated currency, or null>,
  "requested_delivery_date": "<YYYY-MM-DD or null if not specified>",
  "items": [
    {{
      "item_name": "<description>",
      "quantity": <number>,
      "unit": "<pcs|kg|m|l|set|lot|other>",
      "unit_price": <number>,
      "currency": "<currency for this line>"
    }}
  ],
  "flags": ["<zero or more of: blocked_supplier, expired_quote, wrong_total, no_quote, ambiguous_request, unknown_supplier, unknown_cost_center>"],
  "missing_fields": ["<field names that are absent or unresolvable>"],
  "confidence": "<high|medium|low>",
  "notes": "<one sentence of important context, or empty string>"
}}

Rules:
- Set "blocked_supplier" flag if the supplier's status in master data is "blocked".
- Set "expired_quote" if the quote has a validity/expiry date before today ({today}).
- Set "wrong_total" if the quote total does not match the sum of line items.
- Set "no_quote" if no price information is found anywhere.
- Set "ambiguous_request" if the request is too vague to extract meaningful items.
- Set "unknown_supplier" if you cannot map the supplier to master data.
- Set "unknown_cost_center" if cost center cannot be determined even from requester defaults.
- For cost center: if not stated, check if the requester's default_cost_center is known.
- For GL account: pick the best match based on item category.
"""


def extract(
    sender_email: str,
    subject: str,
    body: str,
    quote_texts: list[str] | None = None,
) -> dict:
    """Call Ollama and return the parsed extraction dict.

    Returns a dict matching the JSON schema above, plus:
      "_raw"   — raw LLM response text (for debugging)
      "_error" — set only if the call or parsing failed
    """
    today = date.today().isoformat()
    user_msg = _build_user_prompt(
        sender_email, subject, body, quote_texts or [], today
    )

    try:
        response = ollama.chat(
            model=config.OLLAMA_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            options={"temperature": 0},
        )
        raw = response["message"]["content"]
    except Exception as exc:
        return _error_result("", f"Ollama error: {exc}")

    return _parse_response(raw)


def _parse_response(raw: str) -> dict:
    """Extract the JSON object from the LLM response."""
    cleaned = re.sub(r"```(?:json)?\s*", "", raw).replace("```", "").strip()

    start = cleaned.find("{")
    end = cleaned.rfind("}") + 1
    if start == -1 or end == 0:
        return _error_result(raw, "No JSON object found in LLM response")

    try:
        data = json.loads(cleaned[start:end])
    except json.JSONDecodeError as exc:
        return _error_result(raw, f"JSON parse error: {exc}")

    data["_raw"] = raw
    data.setdefault("flags", [])
    data.setdefault("missing_fields", [])
    data.setdefault("items", [])
    data.setdefault("confidence", "medium")
    return data


def _error_result(raw: str, error: str) -> dict:
    return {
        "_raw": raw,
        "_error": error,
        "flags": ["llm_unavailable"],
        "missing_fields": ["all"],
        "confidence": "low",
        "items": [],
    }
