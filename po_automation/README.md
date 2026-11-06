# PO Automation — FDE Take-Home Challenge

An end-to-end purchase order automation pipeline built in Python. It ingests raw
purchase request emails, extracts structured data using a local LLM via Ollama,
routes the requisition through a configurable approval chain, and submits the approved
order to the mock ERP API. Runs fully offline — no API keys, no subscriptions.

---

## How to run

### 1. Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| Python | 3.11 + | 3.14 works |
| Ollama | latest | Download from https://ollama.com |

After installing Ollama, pull the model:

```powershell
ollama pull llama3.2
```

Ollama runs as a background service automatically after install. You can verify it is
running with `ollama list`.

### 2. Install dependencies

```bash
cd BLP/po_automation
python -m pip install -r requirements.txt
```

### 3. Start the mock ERP API

```bash
# From the challenge_data folder
python "FDE Challenge-4th stage/mock_po_api.py"
# Listens on http://127.0.0.1:8080
```

### 4. Process emails (CLI)

```bash
cd BLP/po_automation
python process_emails.py                              # process all 48 emails
python process_emails.py ../challenge_data/...        # process one specific file
```

### 5. Launch the dashboard

```bash
streamlit run app.py
```

Open http://localhost:8501 in your browser. You can:
- See all requisitions and their state
- Click a row to see extracted data, approval chain, flags
- Approve / Reject at each step (simulating the approver's inbox)
- Drop a new `.eml` file via the sidebar to process it live

---

## Architecture

```
email_parser.py   →   pdf_extractor.py   →   llm_extractor.py
     │                                              │
     └──────────────────────────────────────────────┘
                         │
                   workflow.py  (state machine)
                    ├── master_data.py  (entity resolution, FX)
                    ├── approval_engine.py  (chain builder)
                    ├── database.py  (SQLite)
                    └── po_client.py  (HTTP → mock ERP)
                         │
                       app.py  (Streamlit dashboard)
```

### State machine

```
RECEIVED → EXTRACTING → NEEDS_INFO    (missing required fields)
                      → FLAGGED       (blocked supplier, no quote, ambiguous)
                      → AWAITING_APPROVAL → APPROVED → CREATING_PO → DONE
                                         ↘ REJECTED
                      → FAILED           (ERP error, LLM unreachable)
```

---

## Key design decisions

### Why Ollama + llama3.2?
Runs entirely locally — no API key, no cost, no data leaving the machine. `llama3.2`
is a compact 3B-parameter model that fits in 4 GB of RAM and handles structured JSON
extraction reliably. The model is configurable in `src/config.py` — change to
`llama3.1`, `mistral`, or any other Ollama model you have pulled.

### Why SQLite?
Zero infrastructure — just a file. Every requisition, its extracted data, approval
chain, and log are in one place. For production you'd swap to PostgreSQL with one
config change; the `database.py` module is the only place with SQL.

### Prompt design
The LLM prompt injects the full master data (suppliers, cost centers, employees, GL
accounts) as context. This means entity resolution — "Acme Bearings" → `SUP-001` —
happens inside the LLM call, not in post-processing string matching. It also tells
the model today's date so it can flag expired quotes.

The prompt asks for a fixed JSON schema with a `flags` array (blocked_supplier,
expired_quote, wrong_total, ambiguous_request …) and a `missing_fields` array.
This makes downstream routing deterministic — no regex, no heuristics.

### Approval chain rules
All three rules from `master_data.json` are implemented:
- `self_approval_forbidden` — requester == cost_center_owner → skip that step
- `duplicate_role_collapses` — same person in two roles → appears once
- `approvals_are_sequential` — each step waits for the previous one

### FX conversion
All approval threshold comparisons happen in CHF. Rates come from `master_data.json`.
The original currency is preserved for the ERP submission.

---

## Assumptions

| Topic | Assumption |
|-------|-----------|
| Email sender | The `From:` address is trusted and used to look up the requester employee. |
| `[Attachment: file.pdf]` | Text-style references in plain-text emails are resolved against the `quotes/` folder by filename. |
| Missing delivery date | Passed as `null` to the ERP. The ERP API marks this as a warning, not an error. |
| `cost_centre` on PO | Mapped from cost center code. If absent, the ERP warns but still books. |
| GL account | Best-guess mapping by item category. Not required by the ERP. |
| Blocked supplier | Requisition moves to `FLAGGED` state; a human must intervene. |
| Expired / no quote | Moves to `FLAGGED`. Amount cannot be verified → do not auto-submit. |
| Finance deputy | EMP-702 is `deputy_for` EMP-701. The primary finance approver is used; the deputy is not auto-substituted (would need an escalation timer in production). |

---

## Scaling to 500 requisitions / day

1. **Replace SQLite with PostgreSQL** — already isolated in `database.py`.
2. **Add a task queue** (Celery + Redis or just Python's `concurrent.futures`) — `workflow.process_email()` is stateless; parallelise trivially.
3. **Real email integration** — swap the file-based `email_parser.py` for Microsoft Graph API or IMAP polling.
4. **Approver notifications** — fire actual emails (SMTP / SendGrid) instead of waiting for someone to click in the dashboard.
5. **Prompt caching** — the master-data block is static; Ollama (and Anthropic's API) cache repeated prefixes, so cost stays flat as volume grows.
