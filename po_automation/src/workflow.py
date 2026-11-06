"""Orchestrates the full pipeline for a single email.

State machine:
  RECEIVED → EXTRACTING → NEEDS_INFO (if missing fields)
                        → FLAGGED    (if blocked_supplier etc.)
                        → AWAITING_APPROVAL
                        → APPROVED
                        → CREATING_PO
                        → DONE
  Any step can → FAILED
"""
import json
from pathlib import Path

from . import approval_engine, config, database, email_parser, llm_extractor, master_data, pdf_extractor, po_client


# Fields that must be present before we can route for approval
REQUIRED_FIELDS = {"supplier_id", "cost_center_code", "total_original", "items"}

# Flags that block the process (need manual intervention)
BLOCKING_FLAGS = {"blocked_supplier", "no_quote", "expired_quote", "ambiguous_request", "llm_unavailable", "llm_parse_error"}


def process_email(eml_path: str | Path) -> str:
    """Ingest one .eml file and return the requisition ID."""
    eml_path = Path(eml_path)

    # 1. Parse email
    parsed = email_parser.parse_eml(eml_path)

    rid = database.create_requisition(
        email_file=eml_path.name,
        subject=parsed.subject,
        body=parsed.body,
    )

    _set_state(rid, "EXTRACTING")

    # 2. Extract text from attached PDFs
    quote_texts: list[str] = []
    for fname, pdf_bytes in parsed.attachments:
        text = pdf_extractor.extract_text(pdf_bytes)
        if text and not text.startswith("[PDF extraction error"):
            quote_texts.append(f"[File: {fname}]\n{text}")

    # 3. LLM extraction
    extraction = llm_extractor.extract(
        sender_email=parsed.sender_email,
        subject=parsed.subject,
        body=parsed.body,
        quote_texts=quote_texts,
    )

    raw_llm = extraction.get("_raw", "")
    flags: list[str] = extraction.get("flags", [])
    missing: list[str] = extraction.get("missing_fields", [])

    # Correct blocked_supplier flag against actual master data (small models hallucinate this)
    supplier_id = extraction.get("supplier_id")
    if supplier_id:
        supplier = master_data.get_supplier(supplier_id)
        if supplier:
            if supplier.get("status") == "blocked":
                if "blocked_supplier" not in flags:
                    flags.append("blocked_supplier")
            else:
                flags = [f for f in flags if f != "blocked_supplier"]

    # 4. Resolve requester employee
    requester_emp = master_data.get_employee_by_email(parsed.sender_email)
    requester_id = requester_emp["id"] if requester_emp else None

    # If cost center not found by LLM, fall back to requester's default
    cc_code = extraction.get("cost_center_code")
    if not cc_code and requester_emp:
        cc_code = requester_emp.get("default_cost_center")
        if cc_code and "unknown_cost_center" in missing:
            missing.remove("unknown_cost_center")

    # 5. FX conversion
    total_orig = extraction.get("total_amount")
    currency = extraction.get("currency", "CHF")
    total_chf = master_data.fx_to_chf(total_orig, currency) if total_orig is not None else None

    # 6. Persist extracted data
    database.update_requisition(
        rid,
        requester_email=parsed.sender_email,
        requester_name=parsed.sender,
        requester_employee_id=requester_id,
        supplier_id=extraction.get("supplier_id"),
        supplier_name=extraction.get("supplier_name"),
        cost_center_code=cc_code,
        gl_account_code=extraction.get("gl_account_code"),
        currency=currency,
        total_original=total_orig,
        total_chf=total_chf,
        requested_delivery_date=extraction.get("requested_delivery_date"),
        items_json=json.dumps(extraction.get("items", [])),
        flags_json=json.dumps(flags),
        missing_fields_json=json.dumps(missing),
        raw_llm_response=raw_llm,
    )

    # 7. Decide next state
    blocking = set(flags) & BLOCKING_FLAGS
    if blocking:
        _set_state(rid, "FLAGGED", error=f"Blocking flags: {', '.join(blocking)}")
        return rid

    if missing or not extraction.get("supplier_id") or total_orig is None:
        _set_state(rid, "NEEDS_INFO")
        return rid

    # 8. Build approval chain
    chain = approval_engine.resolve_chain(
        total_chf=total_chf or 0,
        requester_employee_id=requester_id,
        cost_center_code=cc_code,
    )
    database.update_requisition(rid, approval_chain_json=json.dumps(chain))

    # Reject if any required approver could not be resolved
    unresolvable = [s["role"] for s in chain if s.get("employee_id") is None]
    if unresolvable:
        _set_state(rid, "FLAGGED", error=f"Approval chain incomplete — unresolvable roles: {', '.join(unresolvable)}")
        return rid

    if not chain:
        _submit_po(rid)
    else:
        _set_state(rid, "AWAITING_APPROVAL")

    return rid


def approve(rid: str, approver_employee_id: str, comment: str = "") -> bool:
    """Record approval from the current approver. Returns True if chain is complete."""
    req = database.get_requisition(rid)
    if not req or req["state"] != "AWAITING_APPROVAL":
        return False

    chain = json.loads(req["approval_chain_json"] or "[]")
    idx = req["current_approver_index"] or 0

    if idx >= len(chain):
        return False

    step = chain[idx]
    if step["employee_id"] != approver_employee_id:
        return False

    step["status"] = "approved"
    chain[idx] = step

    emp = master_data.get_employee(approver_employee_id)
    database.log_approval(rid, approver_employee_id, emp["name"] if emp else approver_employee_id, "approved", comment)
    database.update_requisition(rid, approval_chain_json=json.dumps(chain), current_approver_index=idx + 1)

    if approval_engine.chain_is_complete(chain):
        _submit_po(rid)
        return True
    return False


def reject(rid: str, approver_employee_id: str, comment: str = "") -> None:
    """Record rejection from the current approver."""
    req = database.get_requisition(rid)
    if not req:
        return

    chain = json.loads(req["approval_chain_json"] or "[]")
    idx = req["current_approver_index"] or 0

    if idx < len(chain):
        chain[idx]["status"] = "rejected"

    emp = master_data.get_employee(approver_employee_id)
    database.log_approval(rid, approver_employee_id, emp["name"] if emp else approver_employee_id, "rejected", comment)
    database.update_requisition(rid, approval_chain_json=json.dumps(chain), state="REJECTED")


def _submit_po(rid: str) -> None:
    _set_state(rid, "CREATING_PO")
    req = database.get_requisition(rid)
    try:
        result = po_client.create_po(req)
    except Exception as exc:
        _set_state(rid, "FAILED", error=f"PO API error: {exc}")
        return

    if "po_number" in result:
        database.update_requisition(rid, po_number=result["po_number"])
        _set_state(rid, "DONE")
    else:
        problems = result.get("problems") or [result.get("error", "unknown")]
        _set_state(rid, "FAILED", error="ERP rejected: " + "; ".join(str(p) for p in problems))


def _set_state(rid: str, state: str, error: str | None = None):
    kwargs: dict = {"state": state}
    if error:
        kwargs["error_message"] = error
    database.update_requisition(rid, **kwargs)
