# PO Automation — Run Guide & Assumptions

End-to-end purchase order automation: reads procurement emails, extracts structured
data with a local LLM, routes through a configurable approval chain, and submits
approved orders to the ERP API.

---

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.11 or later | 3.14 works |
| Ollama | latest | [ollama.com](https://ollama.com) — runs locally, no API key needed |

---

## Running the solution

You need **three things running** at the same time. Open a separate PowerShell window
for each of the first two.

### Window 1 — Mock ERP API

```powershell
venv\Scripts\python.exe "challenge_data\FDE Challenge-4th stage\mock_po_api.py"
```

Leave this running. It listens on `http://127.0.0.1:8080`.
You will see a log line for every PO submission.

### Window 2 — Ollama (if not already running)

Ollama usually starts automatically after install. Check:

```powershell
ollama list
```

If that errors, start it manually:

```powershell
ollama serve
```

### Window 3 — Dashboard

```powershell
..\venv\Scripts\python.exe -m streamlit run app.py
```

Open **http://localhost:8501** in your browser.

---

### Process via the dashboard

In the sidebar, use **"Drop a new .eml here"** to upload and process a single email,
or click **"Process ALL inbox emails"** to run all of them.

---

## Using the dashboard

### Identity selector (sidebar)

Select who you are before doing anything:

| Selection | What you see | What you can do |
|---|---|---|
| Admin (full visibility) | All requisitions + PO history tab | View only, no approvals |
| Any employee | Only requisitions awaiting YOUR approval | Approve or Reject |

### Requisitions tab (Admin)

- Filter by state using the dropdown
- Expand any row to see full details: extracted data, line items, flags, approval workflow
- The workflow timeline shows approvers left to right — green = approved, yellow = waiting, gray = not yet reached

### Purchase Orders tab (Admin)

- Table of all completed POs with PO number, supplier, amounts, approvers, and creation date
- Total value in CHF shown at the bottom

### Approving a request

1. Select your employee identity in the sidebar
2. Only your pending approvals will be visible
3. Expand the row, optionally add a comment, click **Approve** or **Reject**
4. The next approver in the chain becomes active immediately

### Reset the database

rm "C:\Users\I749275\Documents\Projetos\VS\BLP\po_automation\procurement.db" 2>/dev/null && echo "Deleted" || echo "Already gone"

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `llm_unavailable` flag on every email | Ollama not running or model not pulled | Run `ollama list`; if empty, run `ollama pull llama3.2` |
| `Connection refused` on ERP submission | Mock ERP API not running | Start Window 1 (see above) |
| Dashboard won't open | Streamlit not started or port in use | Re-run the streamlit command; check nothing else is on port 8501 |
| Requisition stuck in FAILED | ERP was down when approval completed | Reset the database and reprocess the email |
| `UnicodeEncodeError` in terminal | Windows console encoding | Use PowerShell instead of cmd.exe |

---

## Assumptions

 ### Email sender and content trust
  1. The From: address is trusted as the requester identity.
  2. The content of the email is not verified to avoid prompt injection.

### Cost center fallback:
  1. If the LLM cannot determine the cost center from the email,
  the requester's default_cost_center from master_data.json is used.
  2. If that is also missing, cost_center_code is null and the
  requisition goes to NEEDS_INFO.

### Blocked supplier:
  Requisition moves to FLAGGED. A human must intervene.
  The system never auto-submits to a blocked supplier.

### Expired or missing quote:
  Requisition moves to FAILED. Amount unverified → do not submit.

### Approver substituition:
  No delegation of authority is in place.

### Sequential approvals only:
  The chain is strictly sequential. Parallel approval paths
  (e.g. two approvers at the same tier) are not supported.
