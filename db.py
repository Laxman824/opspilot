"""SQLite persistence: cases, plans, and the step-level audit log."""
from __future__ import annotations

import json
import sqlite3

import pandas as pd

import config
from models import Classification, IncomingRequest, PlannedStep, ToolResult, now_iso

_SCHEMA = """
CREATE TABLE IF NOT EXISTS cases (
    id TEXT PRIMARY KEY,
    channel TEXT, sender TEXT, subject TEXT, body TEXT, received_at TEXT,
    request_type TEXT, urgency TEXT, confidence REAL, rationale TEXT,
    sentiment TEXT, class_source TEXT, department TEXT,
    status TEXT, follow_up_at TEXT,
    memory_note TEXT,
    guardrail_flags TEXT,
    created_at TEXT, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id TEXT REFERENCES cases(id),
    stage TEXT,
    step_order INTEGER, tool TEXT, reason TEXT, params TEXT, origin TEXT
);
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id TEXT REFERENCES cases(id),
    tool TEXT, status TEXT, artifact TEXT,
    executed_at TEXT
);
"""


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _conn() as conn:
        conn.executescript(_SCHEMA)


def upsert_case(req: IncomingRequest, cls: Classification, status: str,
                memory_note: str = "", guardrail_flags: list[str] | None = None) -> None:
    with _conn() as conn:
        conn.execute(
            """INSERT INTO cases (id, channel, sender, subject, body, received_at,
                   request_type, urgency, confidence, rationale, sentiment, class_source,
                   department, status, memory_note, guardrail_flags, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET
                   request_type=excluded.request_type, urgency=excluded.urgency,
                   confidence=excluded.confidence, rationale=excluded.rationale,
                   sentiment=excluded.sentiment, class_source=excluded.class_source,
                   department=excluded.department, status=excluded.status,
                   memory_note=excluded.memory_note,
                   guardrail_flags=excluded.guardrail_flags,
                   updated_at=excluded.updated_at""",
            (req.id, req.channel, req.sender, req.subject, req.body, req.received_at,
             cls.request_type, cls.urgency, cls.confidence, cls.rationale, cls.sentiment,
             cls.source, cls.suggested_department, status, memory_note,
             json.dumps(guardrail_flags or []), now_iso(), now_iso()),
        )


def update_case(case_id: str, **cols) -> None:
    cols["updated_at"] = now_iso()
    assignments = ", ".join(f"{c} = ?" for c in cols)
    with _conn() as conn:
        conn.execute(f"UPDATE cases SET {assignments} WHERE id = ?",
                     (*cols.values(), case_id))


def insert_plan(case_id: str, stage: str, steps: list[PlannedStep]) -> None:
    with _conn() as conn:
        conn.execute("DELETE FROM plans WHERE case_id = ? AND stage = ?", (case_id, stage))
        conn.executemany(
            "INSERT INTO plans (case_id, stage, step_order, tool, reason, params, origin)"
            " VALUES (?,?,?,?,?,?,?)",
            [(case_id, stage, i, s.tool, s.reason, json.dumps(s.params), s.origin)
             for i, s in enumerate(steps)],
        )


def get_plan(case_id: str, stage: str) -> list[PlannedStep]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT tool, reason, params, origin FROM plans"
            " WHERE case_id = ? AND stage = ? ORDER BY step_order",
            (case_id, stage),
        ).fetchall()
    return [PlannedStep(tool=r["tool"], reason=r["reason"],
                        params=json.loads(r["params"] or "{}"), origin=r["origin"])
            for r in rows]


def insert_result(case_id: str, result: ToolResult) -> None:
    with _conn() as conn:
        conn.execute(
            "INSERT INTO audit_log (case_id, tool, status, artifact, executed_at)"
            " VALUES (?,?,?,?,?)",
            (case_id, result.tool, result.status, json.dumps(result.artifact),
             result.executed_at),
        )


def get_case(case_id: str) -> dict | None:
    with _conn() as conn:
        row = conn.execute("SELECT * FROM cases WHERE id = ?", (case_id,)).fetchone()
    return dict(row) if row else None


def get_cases(status: str | None = None) -> pd.DataFrame:
    query = "SELECT * FROM cases"
    params: tuple = ()
    if status:
        query += " WHERE status = ?"
        params = (status,)
    query += " ORDER BY created_at DESC"
    with _conn() as conn:
        return pd.read_sql_query(query, conn, params=params)


def get_audit(case_id: str) -> pd.DataFrame:
    with _conn() as conn:
        return pd.read_sql_query(
            "SELECT tool, status, artifact, executed_at FROM audit_log"
            " WHERE case_id = ? ORDER BY id", conn, params=(case_id,))


def get_sender_cases(sender: str, since_iso: str) -> pd.DataFrame:
    with _conn() as conn:
        return pd.read_sql_query(
            "SELECT * FROM cases WHERE sender = ? AND created_at >= ?"
            " ORDER BY created_at DESC", conn, params=(sender, since_iso))


def get_dashboard_stats() -> dict:
    df = get_cases()
    if df.empty:
        return {"total": 0}
    flags = df["guardrail_flags"].apply(lambda f: bool(json.loads(f or "[]")))
    return {
        "total": len(df),
        "by_type": df["request_type"].value_counts(),
        "by_status": df["status"].value_counts(),
        "by_urgency": df["urgency"].value_counts(),
        "avg_confidence": float(df["confidence"].mean()),
        "pct_overridden": float((df["class_source"] == "human_override").mean() * 100),
        "pct_repaired": float(flags.mean() * 100),
        "pending_review": int((df["status"] == "PENDING_REVIEW").sum()),
        "held_for_human": int((df["status"] == "HELD_FOR_HUMAN").sum()),
        "resolved": int((df["status"] == "RESOLVED").sum()),
        "pending_follow_ups": int(df["follow_up_at"].notna().sum()),
    }
