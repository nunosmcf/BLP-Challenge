"""Determine the approval chain for a requisition.

Rules (from master_data.json):
  - Thresholds are in CHF.
  - self_approval_forbidden: if the requester IS the approver, skip that slot.
  - duplicate_role_collapses: the same person cannot appear twice in the chain.
  - approvals_are_sequential: each step waits for the previous one.
"""
from . import master_data


def build_chain(total_chf: float, requester_employee_id: str | None) -> list[dict]:
    """Return an ordered list of approval steps.

    Each step:
      {
        "role":        str,   # e.g. "cost_center_owner"
        "employee_id": str,
        "employee_name": str,
        "email":       str,
        "status":      "pending" | "approved" | "rejected",
        "cost_center": str | None,
      }
    """
    tiers = master_data.approval_tiers()
    rules = master_data.approval_rules()

    # Find which roles are required
    required_roles: list[str] = []
    for tier in tiers:
        lo = tier["from"]
        hi = tier["to"]
        if hi is None:
            if total_chf >= lo:
                required_roles = tier["required_roles"]
                break
        elif lo <= total_chf <= hi:
            required_roles = tier["required_roles"]
            break

    chain: list[dict] = []
    seen_employee_ids: set[str] = set()

    # We need a cost center to resolve the cost_center_owner.
    # The caller is expected to have set cost_center_code before calling this.
    # We receive it through a second parameter.
    # But to keep the signature simple, we attach cost_center resolution later.
    # Here we build the chain; resolve_chain() fills in the actual employees.

    for role in required_roles:
        employee, cost_center_code = _resolve_role(role, requester_employee_id)
        if employee is None:
            # Role not resolvable — add a placeholder
            chain.append({
                "role": role,
                "employee_id": None,
                "employee_name": f"[{role} — not resolved]",
                "email": None,
                "status": "pending",
                "cost_center": cost_center_code,
            })
            continue

        emp_id = employee["id"]

        # self_approval_forbidden
        if rules.get("self_approval_forbidden") and emp_id == requester_employee_id:
            continue

        # duplicate_role_collapses
        if rules.get("duplicate_role_collapses") and emp_id in seen_employee_ids:
            continue

        seen_employee_ids.add(emp_id)
        chain.append({
            "role": role,
            "employee_id": emp_id,
            "employee_name": employee["name"],
            "email": employee["email"],
            "status": "pending",
            "cost_center": cost_center_code,
        })

    return chain


def _resolve_role(role: str, requester_id: str | None) -> tuple[dict | None, str | None]:
    """Find the employee who fills a given role.

    cost_center_owner: looked up via the requester's default cost center
                       (stored on the requisition — caller must have it).
                       We fall back to checking the employees list directly.
    department_head:   found via the requester's cost center → department.
    finance:           look for role == "finance" in employees list.
    cfo:               role == "cfo".
    ceo:               role == "ceo".
    """
    if role == "cost_center_owner":
        # Resolved by the workflow after we know the cost center.
        # Return a sentinel; resolve_chain_with_cost_center() replaces it.
        return None, None

    if role == "department_head":
        return None, None  # also resolved with cost center context

    if role == "finance":
        employees = master_data.get_employees_by_role("finance")
        for emp in employees:
            if not emp.get("deputy_for"):  # prefer the primary, not the deputy
                return emp, None
        return employees[0] if employees else None, None

    if role == "cfo":
        employees = master_data.get_employees_by_role("cfo")
        return employees[0] if employees else None, None

    if role == "ceo":
        employees = master_data.get_employees_by_role("ceo")
        return employees[0] if employees else None, None

    return None, None


def resolve_chain(
    total_chf: float,
    requester_employee_id: str | None,
    cost_center_code: str | None,
) -> list[dict]:
    """Full resolution: knows about cost center and department.

    This is the function the workflow should call.
    """
    tiers = master_data.approval_tiers()
    rules = master_data.approval_rules()

    required_roles: list[str] = []
    for tier in tiers:
        lo = tier["from"]
        hi = tier["to"]
        if hi is None:
            if total_chf >= lo:
                required_roles = tier["required_roles"]
                break
        elif lo <= total_chf <= hi:
            required_roles = tier["required_roles"]
            break

    chain: list[dict] = []
    seen_ids: set[str] = set()

    cc = master_data.get_cost_center(cost_center_code) if cost_center_code else None

    for role in required_roles:
        emp = None

        if role == "cost_center_owner" and cc:
            emp = master_data.get_employee(cc["owner_employee_id"])
        elif role == "department_head" and cc:
            dept = master_data.get_department(cc["department"])
            if dept:
                emp = master_data.get_employee(dept["head_employee_id"])
        elif role == "finance":
            candidates = master_data.get_employees_by_role("finance")
            emp = next((e for e in candidates if not e.get("deputy_for")), None)
            if not emp and candidates:
                emp = candidates[0]
        elif role == "cfo":
            candidates = master_data.get_employees_by_role("cfo")
            emp = candidates[0] if candidates else None
        elif role == "ceo":
            candidates = master_data.get_employees_by_role("ceo")
            emp = candidates[0] if candidates else None

        if emp is None:
            chain.append({
                "role": role,
                "employee_id": None,
                "employee_name": f"[{role} — unresolvable]",
                "email": None,
                "status": "pending",
            })
            continue

        emp_id = emp["id"]

        if rules.get("self_approval_forbidden") and emp_id == requester_employee_id:
            continue

        if rules.get("duplicate_role_collapses") and emp_id in seen_ids:
            continue

        seen_ids.add(emp_id)
        chain.append({
            "role": role,
            "employee_id": emp_id,
            "employee_name": emp["name"],
            "email": emp["email"],
            "status": "pending",
        })

    return chain


def current_approver(chain: list[dict]) -> dict | None:
    """Return the next pending approver, or None if chain is complete."""
    for step in chain:
        if step["status"] == "pending":
            return step
    return None


def chain_is_complete(chain: list[dict]) -> bool:
    return all(s["status"] == "approved" for s in chain) if chain else True


def chain_is_rejected(chain: list[dict]) -> bool:
    return any(s["status"] == "rejected" for s in chain)
