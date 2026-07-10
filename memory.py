"""Agent memory: what do we know about this sender from past cases?"""
from __future__ import annotations

from datetime import datetime, timedelta

import config
import db


def get_sender_history(sender: str) -> dict:
    since = (datetime.now() - timedelta(days=config.MEMORY_WINDOW_DAYS)).isoformat(
        timespec="seconds")
    past = db.get_sender_cases(sender.strip(), since)
    if past.empty:
        return {"total_cases": 0, "complaints": 0, "urgent": 0,
                "last_case_summary": "", "note": ""}

    complaints = int((past["request_type"] == "Complaint").sum())
    urgent = int((past["request_type"] == "Escalation/Urgent").sum())
    last = past.iloc[0]
    last_summary = (f"{last['id']} ({last['request_type']}, {last['status']}) "
                    f"on {str(last['created_at'])[:10]}: {last['subject']}")

    parts = [f"Sender has {len(past)} prior case(s) in the last "
             f"{config.MEMORY_WINDOW_DAYS} days"]
    detail = []
    if complaints:
        detail.append(f"{complaints} complaint(s)")
    if urgent:
        detail.append(f"{urgent} urgent escalation(s)")
    if detail:
        parts.append("including " + " and ".join(detail))
    note = ", ".join(parts) + f". Most recent: {last_summary}."

    return {"total_cases": len(past), "complaints": complaints, "urgent": urgent,
            "last_case_summary": last_summary, "note": note}
