"""Tool implementations. Every tool: (req, cls, params, ctx) -> ToolResult.

ctx carries cross-step state: kb_section, extracted, draft_texts, follow_up_at,
hold, priority. All artifacts are JSON-serializable dicts — they are what the
operations team sees in the UI and audit trail.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import config
import gemini_client
from models import Classification, IncomingRequest, ToolResult, now_iso


def _result(tool: str, artifact: dict, status: str = "SUCCESS") -> ToolResult:
    return ToolResult(tool=tool, status=status, artifact=artifact,
                      executed_at=now_iso())


def _summary(body: str, limit: int = 140) -> str:
    flat = " ".join(body.split())
    return flat[:limit] + ("…" if len(flat) > limit else "")


# --------------------------------------------------------------------------
# draft_reply — the only tool with sub-styles; the critic reviews its output
# --------------------------------------------------------------------------

_DRAFT_PROMPTS = {
    "ack_empathetic": (
        "Write a short, empathetic acknowledgement email (max 120 words) responding to "
        "this customer complaint. Reference their specific issue. Do not admit fault or "
        "promise compensation. Say a senior handler has been assigned and will respond "
        "within {sla} hours. Sign as 'Customer Operations Team'.\n\nComplaint:\n{body}"
    ),
    "ack_urgent": (
        "Write an urgent, calm, de-escalating acknowledgement (max 100 words). A senior "
        "team member is being assigned immediately and will make contact within 1 hour. "
        "No fault admission, no compensation promises. Sign as 'Customer Operations "
        "Team'.\n\nMessage:\n{body}"
    ),
    "kb_answer": (
        "Answer the customer's question using ONLY this knowledge base excerpt. If it "
        "doesn't cover the question, say you'll check with the team and reply within 1 "
        "business day — do not invent facts. Max 120 words, friendly.\n\n"
        "Knowledge base: {kb_excerpt}\n\nQuestion:\n{body}"
    ),
    "confirmation": (
        "Write a brief confirmation email (max 100 words): the customer's service "
        "request was received and routed to {department}; expected response within "
        "{sla} hours. Summarize their request: {requested_action}. Sign as 'Customer "
        "Operations Team'."
    ),
}

_DRAFT_TEMPLATES = {
    "ack_empathetic": (
        "Dear customer,\n\nThank you for bringing this to our attention — we understand "
        "how frustrating this situation is. Your case has been assigned to a senior "
        "handler who will review it and respond within {sla} hours.\n\n"
        "Customer Operations Team"
    ),
    "ack_urgent": (
        "Dear customer,\n\nWe hear you, and your case is now our immediate priority. A "
        "senior team member is being assigned right now and will contact you within 1 "
        "hour.\n\nCustomer Operations Team"
    ),
    "kb_answer": (
        "Dear customer,\n\nThank you for your question. We're checking the details with "
        "the relevant team and will get back to you within 1 business day.\n\n"
        "Customer Operations Team"
    ),
    "confirmation": (
        "Dear customer,\n\nYour service request has been received and routed to "
        "{department}. You can expect a response within {sla} hours.\n\n"
        "Customer Operations Team"
    ),
}


def draft_reply(req: IncomingRequest, cls: Classification, params: dict,
                ctx: dict) -> ToolResult:
    style = params.get("style", "ack_empathetic")
    if style not in _DRAFT_PROMPTS:
        style = "ack_empathetic"
    sla = config.SLA_HOURS.get(cls.urgency, 24)
    fields = {
        "body": req.body,
        "sla": sla,
        "kb_excerpt": ctx.get("kb_excerpt", config.KNOWLEDGE_BASE["general"]),
        "department": ctx.get("department", cls.suggested_department),
        "requested_action": ctx.get("extracted", {}).get("requested_action",
                                                         _summary(req.body)),
    }
    prompt = _DRAFT_PROMPTS[style].format(**fields)
    fallback = _DRAFT_TEMPLATES[style].format(**fields)
    text, generated_by = gemini_client.generate_text(prompt, fallback)
    ctx.setdefault("draft_texts", {})[style] = text
    ctx["last_draft_style"] = style
    return _result("draft_reply", {"style": style, "draft_text": text,
                                   "generated_by": generated_by})


# --------------------------------------------------------------------------
# Deterministic tools (no API calls)
# --------------------------------------------------------------------------

def lookup_kb(req, cls, params, ctx) -> ToolResult:
    text = f"{req.subject} {req.body}".lower()
    keyword_map = {
        "billing": ["invoice", "bill", "payment", "pay", "charge", "refund", "fee",
                    "upi", "card"],
        "account": ["password", "login", "account", "profile", "email", "closure",
                    "reset"],
        "services": ["install", "support hours", "upgrade", "outage", "coverage",
                     "service", "visit", "timing", "open"],
    }
    section = "general"
    best = 0
    for name, keywords in keyword_map.items():
        hits = sum(1 for k in keywords if k in text)
        if hits > best:
            section, best = name, hits
    ctx["kb_section"] = section
    ctx["kb_excerpt"] = config.KNOWLEDGE_BASE[section]
    return _result("lookup_kb", {"kb_section": section,
                                 "kb_excerpt": config.KNOWLEDGE_BASE[section]})


def extract_details(req, cls, params, ctx) -> ToolResult:
    details = gemini_client.extract_service_details(req.body)
    ctx["extracted"] = details
    return _result("extract_details", details)


def route_department(req, cls, params, ctx) -> ToolResult:
    department = params.get("department") or cls.suggested_department
    if department not in config.DEPARTMENTS:
        department = "General Operations"
    ctx["department"] = department
    note = (f"Case {req.id} routed to {department}. Urgency: {cls.urgency}. "
            f"Summary: {_summary(req.body)}")
    if ctx.get("extracted"):
        note += f" | Extracted details: {ctx['extracted']}"
    return _result("route_department", {
        "department": department,
        "dept_email": config.DEPARTMENTS[department],
        "routing_note": note})


def escalate_case(req, cls, params, ctx) -> ToolResult:
    return _result("escalate_case", {
        "escalated_to": config.SENIOR_HANDLER,
        "summary": f"Case {req.id} ({cls.request_type}, {cls.urgency}) from "
                   f"{req.sender}: {_summary(req.body)}"})


def notify_supervisor(req, cls, params, ctx) -> ToolResult:
    reason = params.get("reason", "flagged for supervisor awareness")
    return _result("notify_supervisor", {
        "alert_to": config.SUPERVISOR,
        "reason": reason,
        "alert_text": f"⚠ SUPERVISOR ALERT — case {req.id} ({cls.urgency}) from "
                      f"{req.sender}. Reason: {reason}. Subject: {req.subject}"})


def log_priority(req, cls, params, ctx) -> ToolResult:
    ctx["priority"] = True
    return _result("log_priority", {"priority_flag": True, "urgency": cls.urgency})


def schedule_follow_up(req, cls, params, ctx) -> ToolResult:
    try:
        hours = float(params.get("hours", 2))
    except (TypeError, ValueError):
        hours = 2.0
    follow_up_at = (datetime.now() + timedelta(hours=hours)).isoformat(
        timespec="seconds")
    ctx["follow_up_at"] = follow_up_at
    return _result("schedule_follow_up", {"follow_up_at": follow_up_at,
                                          "hours": hours})


def set_sla(req, cls, params, ctx) -> ToolResult:
    hours = config.SLA_HOURS.get(cls.urgency, 24)
    deadline = (datetime.now() + timedelta(hours=hours)).isoformat(timespec="seconds")
    ctx["follow_up_at"] = deadline
    return _result("set_sla", {"sla_deadline": deadline, "sla_hours": hours})


def hold_for_human(req, cls, params, ctx) -> ToolResult:
    ctx["hold"] = True
    return _result("hold_for_human", {
        "human_review_required": True,
        "reason": params.get("reason", cls.rationale)})


def send_response(req, cls, params, ctx) -> ToolResult:
    drafts = ctx.get("draft_texts", {})
    style = ctx.get("last_draft_style")
    text = drafts.get(style, "") if style else ""
    if not text:
        return _result("send_response",
                       {"error": "no draft available to send"}, status="FAILED")
    return _result("send_response", {"sent_to": req.sender, "text": text,
                                     "simulated": True})


def mark_resolved(req, cls, params, ctx) -> ToolResult:
    return _result("mark_resolved", {"resolution": "auto_resolved"})


TOOL_REGISTRY = {
    "draft_reply": draft_reply,
    "lookup_kb": lookup_kb,
    "extract_details": extract_details,
    "route_department": route_department,
    "escalate_case": escalate_case,
    "notify_supervisor": notify_supervisor,
    "log_priority": log_priority,
    "schedule_follow_up": schedule_follow_up,
    "set_sla": set_sla,
    "hold_for_human": hold_for_human,
    "send_response": send_response,
    "mark_resolved": mark_resolved,
}

assert set(TOOL_REGISTRY) == set(config.TOOL_NAMES), \
    "TOOL_REGISTRY out of sync with config.TOOL_DESCRIPTIONS"
