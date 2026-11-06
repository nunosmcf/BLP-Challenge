"""SQLite schema and all database helpers.

One module owns the schema. Everything else imports from here — no raw SQL
scattered across the codebase.
"""
import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

from . import config


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    with _connect() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS requisitions (
            id                     TEXT PRIMARY KEY,
            email_file             TEXT,
            email_subject          TEXT,
            email_body             TEXT,
            created_at             TEXT,
            updated_at             TEXT,
            state                  TEXT DEFAULT 'RECEIVED',

            requester_email        TEXT,
            requester_name         TEXT,
            requester_employee_id  TEXT,

            items_json             TEXT,
            supplier_id            TEXT,
            supplier_name          TEXT,
            cost_center_code       TEXT,
            gl_account_code        TEXT,
            currency               TEXT,
            total_original         REAL,
            total_chf              REAL,
            requested_delivery_date TEXT,

            flags_json             TEXT DEFAULT '[]',
            missing_fields_json    TEXT DEFAULT '[]',
            approval_chain_json    TEXT DEFAULT '[]',
            current_approver_index INTEGER DEFAULT 0,

            po_number              TEXT,
            raw_llm_response       TEXT,
            error_message          TEXT
        );

        CREATE TABLE IF NOT EXISTS approval_log (
            id                   INTEGER PRIMARY KEY AUTOINCREMENT,
            requisition_id       TEXT REFERENCES requisitions(id),
            approver_employee_id TEXT,
            approver_name        TEXT,
            action               TEXT,
            timestamp            TEXT,
            comment              TEXT
        );
        """)


def _now() -> str:
    return datetime.utcnow().isoformat()


def create_requisition(email_file: str, subject: str, body: str) -> str:
    rid = str(uuid.uuid4())
    with _connect() as conn:
        conn.execute(
            """INSERT INTO requisitions
               (id, email_file, email_subject, email_body, created_at, updated_at, state)
               VALUES (?, ?, ?, ?, ?, ?, 'RECEIVED')""",
            (rid, email_file, subject, body, _now(), _now()),
        )
    return rid


def update_requisition(rid: str, **fields):
    if not fields:
        return
    fields["updated_at"] = _now()
    sets = ", ".join(f"{k} = ?" for k in fields)
    vals = list(fields.values()) + [rid]
    with _connect() as conn:
        conn.execute(f"UPDATE requisitions SET {sets} WHERE id = ?", vals)


def get_requisition(rid: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM requisitions WHERE id = ?", (rid,)).fetchone()
    return dict(row) if row else None


def all_requisitions() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM requisitions ORDER BY created_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def log_approval(rid: str, employee_id: str, name: str, action: str, comment: str = ""):
    with _connect() as conn:
        conn.execute(
            """INSERT INTO approval_log
               (requisition_id, approver_employee_id, approver_name, action, timestamp, comment)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (rid, employee_id, name, action, _now(), comment),
        )


def get_approval_log(rid: str) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM approval_log WHERE requisition_id = ? ORDER BY timestamp",
            (rid,),
        ).fetchall()
    return [dict(r) for r in rows]


# ── JSON field helpers ──────────────────────────────────────────────────────

def get_json(rid: str, field: str) -> list | dict:
    row = get_requisition(rid)
    if row is None:
        return []
    raw = row.get(field) or "[]"
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
