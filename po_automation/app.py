"""Streamlit dashboard for the Purchase Order Automation POC.

Run:  streamlit run app.py
"""
import json
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))

from src import config, database, master_data, workflow

database.init_db()

STATE_COLOUR = {
    "RECEIVED":          "🔵",
    "EXTRACTING":        "🔄",
    "NEEDS_INFO":        "🟡",
    "FLAGGED":           "🔴",
    "AWAITING_APPROVAL": "🟡",
    "APPROVED":          "🟢",
    "CREATING_PO":       "🔄",
    "DONE":              "✅",
    "FAILED":            "❌",
    "REJECTED":          "🚫",
}


def _initials(name: str) -> str:
    parts = name.split()
    return (parts[0][0] + parts[-1][0]).upper() if len(parts) >= 2 else name[:2].upper()


def render_approval_timeline(chain: list, current_idx: int):
    """Render a smooth horizontal timeline: small end caps, approver circles on the line."""
    if not chain:
        return

    n = len(chain)
    LINE_Y = 26      # px from top to line center
    CIRCLE_D = 38    # approver circle diameter
    CAP_D = 10       # end cap diameter

    def _colors(i, step):
        status = step.get("status", "pending")
        if status == "approved":
            return "#22c55e", "#16a34a", "white"
        if status == "rejected":
            return "#ef4444", "#dc2626", "white"
        if i == current_idx:
            return "#eab308", "#ca8a04", "white"
        return "#ffffff", "#d1d5db", "#9ca3af"

    nodes = ""

    # Green progress segment (covers approved steps)
    if current_idx > 0:
        progress_pct = current_idx / (n + 1) * 100
        nodes += (
            f'<div style="position:absolute;top:{LINE_Y}px;left:0;width:{progress_pct:.2f}%;'
            f'height:2px;background:#22c55e;transform:translateY(-50%);z-index:1"></div>'
        )
    # Orange segment to current step
    if current_idx < n:
        seg_start = current_idx / (n + 1) * 100
        seg_end   = (current_idx + 1) / (n + 1) * 100
        nodes += (
            f'<div style="position:absolute;top:{LINE_Y}px;left:{seg_start:.2f}%;'
            f'width:{seg_end - seg_start:.2f}%;height:2px;background:#fde047;'
            f'transform:translateY(-50%);z-index:1"></div>'
        )

    # Start cap
    nodes += (
        f'<div style="position:absolute;top:{LINE_Y}px;left:0;'
        f'transform:translate(-50%,-50%);width:{CAP_D}px;height:{CAP_D}px;'
        f'border-radius:50%;background:#9ca3af;z-index:3;'
        f'box-shadow:0 0 0 3px #f3f4f6"></div>'
    )
    # End cap
    end_bg = "#22c55e" if current_idx >= n else "#9ca3af"
    nodes += (
        f'<div style="position:absolute;top:{LINE_Y}px;left:100%;'
        f'transform:translate(-50%,-50%);width:{CAP_D}px;height:{CAP_D}px;'
        f'border-radius:50%;background:{end_bg};z-index:3;'
        f'box-shadow:0 0 0 3px #f3f4f6"></div>'
    )

    # Approver nodes
    for i, step in enumerate(chain):
        pct = (i + 1) / (n + 1) * 100
        bg, border, text = _colors(i, step)
        name = step.get("employee_name", "?")
        role = step.get("role", "")
        ini = _initials(name)

        nodes += (
            f'<div style="position:absolute;left:{pct:.2f}%;top:{LINE_Y}px;'
            f'transform:translate(-50%,-50%);'
            f'display:flex;flex-direction:column;align-items:center;z-index:4">'

            f'<div style="width:{CIRCLE_D}px;height:{CIRCLE_D}px;border-radius:50%;'
            f'background:{bg};border:2px solid {border};'
            f'display:flex;align-items:center;justify-content:center;'
            f'font-weight:700;font-size:13px;color:{text};'
            f'box-shadow:0 2px 6px rgba(0,0,0,0.14)">{ini}</div>'

            f'<div style="margin-top:9px;font-size:11px;font-weight:600;color:#ffffff;'
            f'white-space:nowrap;max-width:80px;overflow:hidden;'
            f'text-overflow:ellipsis;text-align:center">{name}</div>'

            f'<div style="font-size:10px;color:#e5e7eb;white-space:nowrap;'
            f'max-width:80px;overflow:hidden;text-overflow:ellipsis;'
            f'text-align:center;margin-top:1px">{role}</div>'

            '</div>'
        )

    html = (
        f'<div style="position:relative;height:100px;margin:8px 20px 4px;">'
        f'<div style="position:absolute;top:{LINE_Y}px;left:0;right:0;height:2px;'
        f'background:#e5e7eb;transform:translateY(-50%);z-index:0"></div>'
        f'{nodes}'
        f'</div>'
    )
    st.markdown(html, unsafe_allow_html=True)


def render_detail(req: dict, logged_in_id: str | None, is_admin: bool):
    c1, c2 = st.columns(2)

    with c1:
        st.markdown(f"**ID:** `{req['id'][:8]}…`")
        st.markdown(f"**From:** {req.get('requester_name') or '—'} `{req.get('requester_email') or ''}`")
        st.markdown(f"**Subject:** {req.get('email_subject') or '—'}")
        st.markdown(f"**State:** {req['state']}")
        if req.get("po_number"):
            st.success(f"PO Number: **{req['po_number']}**")
        if req.get("error_message"):
            st.error(req["error_message"])

    with c2:
        st.markdown(f"**Supplier:** {req.get('supplier_name') or '—'}  `{req.get('supplier_id') or ''}`")
        st.markdown(f"**Cost Centre:** {req.get('cost_center_code') or '—'}")
        st.markdown(f"**GL Account:** {req.get('gl_account_code') or '—'}")
        if req.get("total_original") is not None:
            st.markdown(
                f"**Total:** {req['total_original']:,.2f} {req.get('currency', '')} "
                f"-> **{req.get('total_chf') or 0:,.2f} CHF**"
            )
        if req.get("requested_delivery_date"):
            st.markdown(f"**Delivery:** {req['requested_delivery_date']}")

    items = json.loads(req.get("items_json") or "[]")
    if items:
        st.markdown("**Line items:**")
        for item in items:
            st.markdown(
                f"- {item.get('quantity')} x {item.get('unit', 'pcs')} "
                f"**{item.get('item_name')}** "
                f"@ {item.get('unit_price')} {item.get('currency', '')}"
            )

    missing = json.loads(req.get("missing_fields_json") or "[]")
    if missing:
        st.warning(f"Missing fields: {', '.join(missing)}")

    flags = json.loads(req.get("flags_json") or "[]")
    if flags:
        st.error(f"Flags: {', '.join(flags)}")

    chain = json.loads(req.get("approval_chain_json") or "[]")
    current_idx = req.get("current_approver_index") or 0

    if chain:
        st.markdown("**Approval workflow:**")
        render_approval_timeline(chain, current_idx)

        if req["state"] == "AWAITING_APPROVAL" and current_idx < len(chain):
            current_step = chain[current_idx]

            if is_admin:
                st.info(f"Waiting for **{current_step['employee_name']}** ({current_step['role']}) — admin view only.")
            elif not logged_in_id:
                st.info("Select your identity in the sidebar to approve or reject.")
            elif logged_in_id != current_step["employee_id"]:
                st.warning(
                    f"Only **{current_step['employee_name']}** can act on this step. "
                    "Switch identity in the sidebar."
                )
            else:
                comment_key = f"comment_{req['id']}"
                confirm_key = f"confirm_{req['id']}"
                st.text_input("Comment (optional)", key=comment_key)

                col_a, col_r = st.columns(2)
                with col_a:
                    if st.button("Approve", key=f"approve_{req['id']}"):
                        st.session_state[confirm_key] = "approve"
                with col_r:
                    if st.button("Reject", key=f"reject_{req['id']}"):
                        st.session_state[confirm_key] = "reject"

                pending = st.session_state.get(confirm_key)
                if pending == "approve":
                    st.warning(f"Confirm approval of **{req['email_file']}**?")
                    c1, c2 = st.columns(2)
                    with c1:
                        if st.button("Yes, approve", key=f"confirm_yes_{req['id']}"):
                            workflow.approve(req["id"], current_step["employee_id"],
                                             st.session_state.get(comment_key, ""))
                            del st.session_state[confirm_key]
                            st.rerun()
                    with c2:
                        if st.button("Cancel", key=f"confirm_no_a_{req['id']}"):
                            del st.session_state[confirm_key]
                            st.rerun()

                elif pending == "reject":
                    st.error(f"Confirm rejection of **{req['email_file']}**?")
                    c1, c2 = st.columns(2)
                    with c1:
                        if st.button("Yes, reject", key=f"confirm_yes_r_{req['id']}"):
                            workflow.reject(req["id"], current_step["employee_id"],
                                            st.session_state.get(comment_key, "Rejected"))
                            del st.session_state[confirm_key]
                            st.rerun()
                    with c2:
                        if st.button("Cancel", key=f"confirm_no_r_{req['id']}"):
                            del st.session_state[confirm_key]
                            st.rerun()

    log = database.get_approval_log(req["id"])
    if log:
        st.markdown("**Approval log:**")
        for entry in log:
            icon = "✅" if entry["action"] == "approved" else "❌"
            st.markdown(f"{icon} {entry['approver_name']} — {entry['timestamp'][:16]}  {entry.get('comment') or ''}")


# ── Sidebar ─────────────────────────────────────────────────────────────────
st.sidebar.title("PO Automation")
st.sidebar.markdown("---")

# Identity selector
employees = master_data.load()["employees"]
emp_options = {f"{e['name']} ({e['role']})": e["id"] for e in employees}
identity_options = ["Admin (full visibility)", "— select employee —"] + list(emp_options.keys())

logged_in_label = st.sidebar.selectbox("Logged in as", options=identity_options, key="logged_in_label")

is_admin = logged_in_label == "Admin (full visibility)"
logged_in_id = emp_options.get(logged_in_label) if not is_admin else None

if is_admin:
    st.sidebar.caption("Viewing all requisitions. Approval actions disabled.")
elif logged_in_id:
    st.sidebar.caption("Showing only requisitions awaiting your approval.")

st.sidebar.markdown("---")

uploaded = st.sidebar.file_uploader("Drop a new .eml here", type="eml")
if uploaded:
    if st.sidebar.button("Process this email"):
        tmp = Path(Path(uploaded.name).name)
        tmp.write_bytes(uploaded.getvalue())
        with st.spinner("Calling Ollama..."):
            rid = workflow.process_email(tmp)
        tmp.unlink(missing_ok=True)
        req = database.get_requisition(rid)
        st.sidebar.success(f"{req['state']} -> `{rid[:8]}`")
        st.rerun()




# ── Main ─────────────────────────────────────────────────────────────────────
st.title("Purchase Order Pipeline")

all_reqs = database.all_requisitions()

if not all_reqs:
    st.info("No requisitions yet. Use the sidebar to process emails.")
    st.stop()

# Filter by identity
if is_admin or not logged_in_id:
    visible_reqs = all_reqs
else:
    visible_reqs = [
        r for r in all_reqs
        if r["state"] == "AWAITING_APPROVAL"
        and (lambda chain, idx: idx < len(chain) and chain[idx]["employee_id"] == logged_in_id)(
            json.loads(r.get("approval_chain_json") or "[]"),
            r.get("current_approver_index") or 0,
        )
    ]

# Stats (always from full dataset)
states = [r["state"] for r in all_reqs]
cols = st.columns(5)
cols[0].metric("Total",                len(all_reqs))
cols[1].metric("Awaiting Approval",    states.count("AWAITING_APPROVAL"))
cols[2].metric("Needs Info / Flagged", states.count("NEEDS_INFO") + states.count("FLAGGED"))
cols[3].metric("Done",                 states.count("DONE"))
cols[4].metric("Failed / Rejected",    states.count("FAILED") + states.count("REJECTED"))

st.markdown("---")

# ── Admin: tabbed view ────────────────────────────────────────────────────────
if is_admin:
    tab_reqs, tab_pos = st.tabs(["Requisitions", "Purchase Orders"])

    with tab_reqs:
        filter_options = ["All"] + sorted({r["state"] for r in visible_reqs})
        filter_state = st.selectbox("Filter by state", filter_options, key="admin_filter")
        display_reqs = visible_reqs if filter_state == "All" else [r for r in visible_reqs if r["state"] == filter_state]

        for req in display_reqs:
            icon = STATE_COLOUR.get(req["state"], "⚪")
            flags = json.loads(req.get("flags_json") or "[]")
            flag_str = "  flag: " + " · ".join(flags) if flags else ""
            label = f"{icon} **{req['email_file']}** — {req['state']}{flag_str}"
            with st.expander(label):
                render_detail(req, logged_in_id, is_admin)

    with tab_pos:
        done_reqs = [r for r in all_reqs if r["state"] == "DONE" and r.get("po_number")]

        if not done_reqs:
            st.info("No purchase orders have been created yet.")
        else:
            import pandas as pd

            rows = []
            for r in done_reqs:
                chain = json.loads(r.get("approval_chain_json") or "[]")
                approvers = " → ".join(s["employee_name"] for s in chain)
                rows.append({
                    "PO Number":      r["po_number"],
                    "Supplier":       r.get("supplier_name") or "—",
                    "Requester":      r.get("requester_name") or r.get("requester_email") or "—",
                    "Amount":         f"{r['total_original']:,.2f} {r.get('currency', '')}" if r.get("total_original") else "—",
                    "Total CHF":      f"{r['total_chf']:,.2f}" if r.get("total_chf") else "—",
                    "Delivery":       r.get("requested_delivery_date") or "—",
                    "Approved by":    approvers or "—",
                    "Created":        (r.get("updated_at") or "")[:16],
                })

            df = pd.DataFrame(rows)
            st.dataframe(df, use_container_width=True, hide_index=True)

            total_chf = sum(r["total_chf"] for r in done_reqs if r.get("total_chf"))
            st.markdown(f"**{len(done_reqs)} purchase order(s) — total value: {total_chf:,.2f} CHF**")

# ── Approver view ─────────────────────────────────────────────────────────────
else:
    if not logged_in_id:
        st.info("Select your identity in the sidebar.")
        st.stop()

    if not visible_reqs:
        st.success("No pending approvals for you right now.")
        st.stop()

    for req in visible_reqs:
        icon = STATE_COLOUR.get(req["state"], "⚪")
        flags = json.loads(req.get("flags_json") or "[]")
        flag_str = "  flag: " + " · ".join(flags) if flags else ""
        label = f"{icon} **{req['email_file']}** — {req['state']}{flag_str}"
        with st.expander(label):
            render_detail(req, logged_in_id, is_admin)
