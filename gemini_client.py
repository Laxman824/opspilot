"""All Gemini access lives here, behind a three-tier resilience chain:
primary model w/ backoff -> fallback model -> deterministic offline fallback.
The app must stay fully demoable with no API key and through quota errors.
"""
from __future__ import annotations

import json
import time

import config
import guardrails
from models import Classification, PlannedStep

try:
    from google import genai
    from google.genai import types
    _SDK_AVAILABLE = True
except ImportError:  # keeps unit tests runnable without the SDK
    _SDK_AVAILABLE = False

_client = None


def _get_client():
    global _client
    if _client is None and _SDK_AVAILABLE and config.GEMINI_API_KEY:
        _client = genai.Client(api_key=config.GEMINI_API_KEY)
    return _client


def api_available() -> bool:
    return _get_client() is not None


_TRANSIENT_MARKERS = ("429", "RESOURCE_EXHAUSTED", "500", "503", "UNAVAILABLE",
                      "DEADLINE", "timeout", "Timeout", "overloaded")


def _generate(contents: str, gen_config) -> str:
    """Resilience tiers 1+2. Raises on total failure (caller applies tier 3)."""
    client = _get_client()
    if client is None:
        raise RuntimeError("Gemini API not configured")

    last_error: Exception | None = None
    for model in (config.PRIMARY_MODEL, config.FALLBACK_MODEL):
        attempts = config.MAX_RETRIES if model == config.PRIMARY_MODEL else 1
        for attempt in range(attempts):
            try:
                response = client.models.generate_content(
                    model=model, contents=contents, config=gen_config)
                if not response.text:
                    raise RuntimeError("empty response")
                return response.text
            except Exception as e:  # noqa: BLE001 — every failure moves down the chain
                last_error = e
                if any(m in str(e) for m in _TRANSIENT_MARKERS):
                    time.sleep(config.RETRY_BASE_DELAY * (2 ** attempt))
                else:
                    break  # non-transient: skip retries, try next model
    raise last_error  # type: ignore[misc]


# --------------------------------------------------------------------------
# 1. Fused triage + planning call
# --------------------------------------------------------------------------

def _plan_schema():
    return types.Schema(
        type=types.Type.OBJECT,
        properties={
            "request_type": types.Schema(type=types.Type.STRING,
                                         enum=config.REQUEST_TYPES),
            "urgency": types.Schema(type=types.Type.STRING,
                                    enum=config.URGENCY_LEVELS),
            "confidence": types.Schema(type=types.Type.NUMBER),
            "sentiment": types.Schema(type=types.Type.STRING,
                                      enum=config.SENTIMENTS),
            "rationale": types.Schema(type=types.Type.STRING),
            "suggested_department": types.Schema(
                type=types.Type.STRING, enum=list(config.DEPARTMENTS.keys())),
            "memory_impact": types.Schema(type=types.Type.STRING),
            "plan": types.Schema(
                type=types.Type.ARRAY,
                items=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "tool": types.Schema(type=types.Type.STRING,
                                             enum=config.TOOL_NAMES),
                        "reason": types.Schema(type=types.Type.STRING),
                        "params_json": types.Schema(type=types.Type.STRING),
                    },
                    required=["tool", "reason", "params_json"],
                ),
            ),
        },
        required=["request_type", "urgency", "confidence", "sentiment", "rationale",
                  "suggested_department", "memory_impact", "plan"],
    )


_PLANNER_PROMPT = """You are OpsPilot, an autonomous triage agent for a customer operations desk. For the
incoming request below, produce (a) a classification and (b) a remediation PLAN as an
ordered list of tool calls chosen from the tool catalog.

## Request types
- "Complaint": dissatisfaction, poor-service grievance, billing dispute framed as a wrong
  done to the customer, demand for remediation.
- "General Enquiry": asks for information only (pricing, policy, how-to, hours); no
  operational action, no grievance.
- "Service Request": asks us to DO something: install, repair, upgrade, change plan,
  update details, schedule a visit.
- "Escalation/Urgent": threats to cancel/legal/regulatory action, repeated unresolved
  contacts, safety issues, total outage, or extreme distress needing a human now.

## Urgency (judge independently of type)
Low = informational; Medium = operational, normal timeline; High = significant impact or
strong dissatisfaction; Critical = churn/safety/legal risk or total outage.

## Tool catalog
{tool_catalog}

## Playbook policy (you MUST respect it; violations will be corrected and flagged)
{playbook_text}

## Planning rules
1. Include every mandatory tool for your chosen type, in a sensible order.
2. Add optional tools ONLY when this specific request justifies them — give the concrete
   reason (e.g., repeat complainant, churn risk, explicit deadline).
3. Never include forbidden tools. Maximum 6 steps.
4. Each step's "reason" must cite specifics from the request or sender history.
5. confidence = your honest probability (0.0-1.0) that request_type is correct. If the
   request is ambiguous or mixes types, set it below 0.7 so a human reviews it.
6. params_json: a JSON object string with the tool's params, "{{}}" if none.

## Sender history (agent memory)
{memory_note}
If history shows prior complaints or urgent cases, consider raising urgency and adding
notify_supervisor, and say so in memory_impact (otherwise set memory_impact to "none").

## Incoming request
Sender: {sender}
Subject: {subject}
Body:
{body}
"""


def keyword_fallback(req) -> tuple[Classification, list[PlannedStep], str]:
    """Tier 3: deterministic triage. confidence=0.5 forces human review by design."""
    text = f"{req.subject} {req.body}".lower()
    rules = [
        ("Escalation/Urgent", "Critical",
         ["cancel", "lawyer", "legal", "urgent", "immediately", "furious",
          "last time", "consumer forum"]),
        ("Complaint", "High",
         ["unacceptable", "disappointed", "complaint", "refund", "worst",
          "dispute", "overcharged", "no-show"]),
        ("Service Request", "Medium",
         ["install", "upgrade", "schedule", "change my plan", "update my address",
          "repair", "new address", "add a"]),
    ]
    rtype, urgency, hit = "General Enquiry", "Low", "no action keywords found"
    for rule_type, rule_urgency, keywords in rules:
        matched = [k for k in keywords if k in text]
        if matched:
            rtype, urgency, hit = rule_type, rule_urgency, f"matched keywords: {matched}"
            break

    cls = Classification(
        request_type=rtype, urgency=urgency, confidence=0.5,
        rationale=f"Offline keyword triage ({hit}). Confidence capped at 0.5 so a "
                  f"human reviews this case.",
        sentiment="calm", suggested_department="General Operations",
        source="keyword_fallback")
    plan = guardrails.default_plan(rtype, "default playbook (offline fallback)")
    return cls, plan, "none"


def plan_request(req, memory_note: str) -> tuple[Classification, list[PlannedStep], str]:
    """Returns (classification, proposed_plan, memory_impact)."""
    try:
        raw = _generate(
            _PLANNER_PROMPT.format(
                tool_catalog=guardrails.tool_catalog_text(),
                playbook_text=guardrails.playbook_prompt_text(),
                memory_note=memory_note or "First contact — no prior history.",
                sender=req.sender, subject=req.subject, body=req.body),
            types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=_plan_schema(),
                temperature=0.2),
        )
        data = json.loads(raw)
        if data["request_type"] not in config.REQUEST_TYPES:
            raise ValueError(f"invalid request_type: {data['request_type']}")
        cls = Classification(
            request_type=data["request_type"],
            urgency=data["urgency"] if data["urgency"] in config.URGENCY_LEVELS
            else "Medium",
            confidence=max(0.0, min(1.0, float(data["confidence"]))),
            rationale=data["rationale"],
            sentiment=data["sentiment"] if data["sentiment"] in config.SENTIMENTS
            else "calm",
            suggested_department=data["suggested_department"]
            if data["suggested_department"] in config.DEPARTMENTS
            else "General Operations",
            source="gemini")
        plan = []
        for step in data["plan"]:
            try:
                params = json.loads(step.get("params_json") or "{}")
                if not isinstance(params, dict):
                    params = {}
            except (json.JSONDecodeError, TypeError):
                params = {}
            plan.append(PlannedStep(tool=step["tool"], reason=step["reason"],
                                    params=params, origin="agent"))
        return cls, plan, data.get("memory_impact", "none")
    except Exception:  # noqa: BLE001 — any failure degrades to offline triage
        return keyword_fallback(req)


# --------------------------------------------------------------------------
# 2. Free-text generation (drafts)
# --------------------------------------------------------------------------

def generate_text(prompt: str, fallback_text: str,
                  temperature: float = 0.4) -> tuple[str, str]:
    """Returns (text, generated_by) with generated_by in {gemini, template_fallback}."""
    try:
        text = _generate(prompt,
                         types.GenerateContentConfig(temperature=temperature))
        return text.strip(), "gemini"
    except Exception:  # noqa: BLE001
        return fallback_text, "template_fallback"


# --------------------------------------------------------------------------
# 3. Structured detail extraction (service requests)
# --------------------------------------------------------------------------

_EXTRACT_FIELDS = ["service_type", "account_reference", "requested_action",
                   "preferred_timing"]


def extract_service_details(body: str) -> dict:
    try:
        schema = types.Schema(
            type=types.Type.OBJECT,
            properties={f: types.Schema(type=types.Type.STRING)
                        for f in _EXTRACT_FIELDS},
            required=_EXTRACT_FIELDS)
        raw = _generate(
            "Extract these fields from the service request below. Use the customer's "
            "own words where possible; write \"not provided\" for anything absent.\n"
            "- service_type: which service/product is involved\n"
            "- account_reference: any account/customer/order reference\n"
            "- requested_action: what they want done\n"
            "- preferred_timing: any dates, deadlines or preferences\n\n"
            f"Service request:\n{body}",
            types.GenerateContentConfig(response_mime_type="application/json",
                                        response_schema=schema, temperature=0.1))
        data = json.loads(raw)
        return {f: str(data.get(f) or "not provided") for f in _EXTRACT_FIELDS}
    except Exception:  # noqa: BLE001
        return {f: "not provided" for f in _EXTRACT_FIELDS}


# --------------------------------------------------------------------------
# 4. Critic agent (reflection on customer-facing drafts)
# --------------------------------------------------------------------------

_CRITIC_PROMPT = """You are a compliance reviewer for customer communications at an operations desk.
Review the draft below against this checklist:
1. No admission of fault or liability.
2. No promise of compensation, refund, or specific outcome not yet approved.
3. If it claims facts (policies, hours, timelines), they must come from the provided
   context — no invented facts.
4. Tone matches the situation ({draft_kind}): empathetic for complaints, calm and
   de-escalating for urgent cases, clear and friendly otherwise.
5. Under 150 words, addresses the customer's actual message.

Customer message: {request_body}
Draft to review:
{draft}

If ALL checks pass: approved=true, issues=[], revised_text="".
If any fail: approved=false, list each issue, and provide revised_text that fixes every
issue while preserving intent.
"""


def critique_draft(draft: str, request_body: str, draft_kind: str) -> dict:
    try:
        schema = types.Schema(
            type=types.Type.OBJECT,
            properties={
                "approved": types.Schema(type=types.Type.BOOLEAN),
                "issues": types.Schema(type=types.Type.ARRAY,
                                       items=types.Schema(type=types.Type.STRING)),
                "revised_text": types.Schema(type=types.Type.STRING),
            },
            required=["approved", "issues", "revised_text"])
        raw = _generate(
            _CRITIC_PROMPT.format(draft_kind=draft_kind, request_body=request_body,
                                  draft=draft),
            types.GenerateContentConfig(response_mime_type="application/json",
                                        response_schema=schema, temperature=0.1))
        data = json.loads(raw)
        return {"approved": bool(data["approved"]),
                "issues": [str(i) for i in data.get("issues", [])],
                "revised_text": str(data.get("revised_text") or ""),
                "available": True}
    except Exception:  # noqa: BLE001
        return {"approved": True, "issues": ["critic unavailable — draft shipped unreviewed"],
                "revised_text": "", "available": False}
