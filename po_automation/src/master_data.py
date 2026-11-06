"""Load and query master_data.json.

Acts as the single source of truth for all reference data lookups.
"""
import json
from functools import lru_cache
from pathlib import Path

from . import config


@lru_cache(maxsize=1)
def load() -> dict:
    with open(config.MASTER_DATA, encoding="utf-8") as fh:
        return json.load(fh)


# ── Lookups ────────────────────────────────────────────────────────────────

def get_employee_by_email(email: str) -> dict | None:
    email = email.lower().strip()
    for emp in load()["employees"]:
        if emp["email"].lower() == email:
            return emp
    return None


def get_employee(employee_id: str) -> dict | None:
    for emp in load()["employees"]:
        if emp["id"] == employee_id:
            return emp
    return None


def get_employees_by_role(role: str) -> list[dict]:
    return [e for e in load()["employees"] if e.get("role") == role]


def get_cost_center(code: str) -> dict | None:
    for cc in load()["cost_centers"]:
        if cc["code"] == code:
            return cc
    return None


def get_department(code: str) -> dict | None:
    for dept in load()["departments"]:
        if dept["code"] == code:
            return dept
    return None


def get_supplier(supplier_id: str) -> dict | None:
    for sup in load()["suppliers"]:
        if sup["id"] == supplier_id:
            return sup
    return None


def find_supplier_by_name(name: str) -> dict | None:
    """Best-effort fuzzy match on supplier name (case-insensitive substring)."""
    name_lower = name.lower()
    # Exact match first
    for sup in load()["suppliers"]:
        if sup["name"].lower() == name_lower:
            return sup
    # Substring match
    for sup in load()["suppliers"]:
        if name_lower in sup["name"].lower() or sup["name"].lower() in name_lower:
            return sup
    return None


def get_gl_account(code: str) -> dict | None:
    for gl in load()["gl_accounts"]:
        if gl["code"] == code:
            return gl
    return None


def fx_to_chf(amount: float, currency: str) -> float:
    """Convert an amount to CHF using master data FX rates."""
    rates = load().get("_meta", {}).get("fx_rates_to_chf", config.FX_TO_CHF)
    rate = rates.get(currency.upper(), 1.0)
    return round(amount * rate, 2)


def approval_tiers() -> list[dict]:
    return load()["approval_limits_chf"]


def approval_rules() -> dict:
    return load().get("rules", {})


def all_suppliers_summary() -> str:
    """Compact supplier list for LLM context."""
    lines = []
    for s in load()["suppliers"]:
        lines.append(f"  {s['id']} | {s['name']} | {s['country']} | {s['default_currency']} | status:{s['status']}")
    return "\n".join(lines)


def all_cost_centers_summary() -> str:
    lines = []
    for cc in load()["cost_centers"]:
        lines.append(f"  {cc['code']} | {cc['name']}")
    return "\n".join(lines)


def all_employees_summary() -> str:
    lines = []
    for e in load()["employees"]:
        lines.append(f"  {e['id']} | {e['name']} | {e['email']} | {e['role']}")
    return "\n".join(lines)


def all_gl_accounts_summary() -> str:
    lines = []
    for g in load()["gl_accounts"]:
        lines.append(f"  {g['code']} | {g['name']}")
    return "\n".join(lines)
