"""Policy guardrails: the agent proposes a plan, policy disposes.

A playbook entry key is either a bare tool name ("escalate_case") or
"draft_reply:<style>" to pin the draft style for that branch.
"""
from __future__ import annotations

import config
from models import CaseStatus, PlannedStep

PLAYBOOKS = {
    "Complaint": {
        "mandatory": ["draft_reply:ack_empathetic", "escalate_case", "log_priority",
                      "schedule_follow_up"],
        "optional": ["notify_supervisor", "send_response"],
        "forbidden": ["mark_resolved", "hold_for_human"],
        "terminal_status": CaseStatus.ESCALATED,
    },
    "General Enquiry": {
        "mandatory": ["lookup_kb", "draft_reply:kb_answer", "send_response",
                      "mark_resolved"],
        "optional": ["schedule_follow_up"],
        "forbidden": ["notify_supervisor", "escalate_case", "hold_for_human"],
        "terminal_status": CaseStatus.RESOLVED,
    },
    "Service Request": {
        "mandatory": ["extract_details", "route_department", "draft_reply:confirmation",
                      "set_sla"],
        "optional": ["schedule_follow_up", "send_response"],
        "forbidden": ["mark_resolved", "hold_for_human"],
        "terminal_status": CaseStatus.ROUTED,
    },
    "Escalation/Urgent": {
        "mandatory": ["hold_for_human", "draft_reply:ack_urgent", "notify_supervisor"],
        "optional": ["log_priority", "escalate_case"],
        "forbidden": ["mark_resolved", "send_response"],
        "terminal_status": CaseStatus.HELD_FOR_HUMAN,
    },
}

MAX_PLAN_STEPS = 6

_DEFAULT_PARAMS = {
    "schedule_follow_up": {"hours": 2},
    "hold_for_human": {"reason": "critical case — human handling required by policy"},
    "notify_supervisor": {"reason": "critical case flagged for supervisor awareness"},
}


def _key_matches(step: PlannedStep, playbook_key: str) -> bool:
    if ":" in playbook_key:
        tool, style = playbook_key.split(":", 1)
        return step.tool == tool and step.params.get("style") == style
    return step.tool == playbook_key


def _step_from_key(playbook_key: str, reason: str, origin: str) -> PlannedStep:
    if ":" in playbook_key:
        tool, style = playbook_key.split(":", 1)
        return PlannedStep(tool=tool, reason=reason, params={"style": style},
                           origin=origin)
    params = dict(_DEFAULT_PARAMS.get(playbook_key, {}))
    return PlannedStep(tool=playbook_key, reason=reason, params=params, origin=origin)


def _canonical_index(step: PlannedStep, canonical: list[str]) -> int:
    for i, key in enumerate(canonical):
        if _key_matches(step, key):
            return i
    return len(canonical)  # unknown-but-allowed steps sort last


def validate_and_repair_plan(plan: list[PlannedStep],
                             request_type: str) -> tuple[list[PlannedStep], list[str]]:
    """Return (final_plan, flags). Empty flags == the agent's plan was fully compliant."""
    playbook = PLAYBOOKS[request_type]
    flags: list[str] = []
    kept: list[PlannedStep] = []

    for step in plan:
        if step.tool not in config.TOOL_NAMES:
            flags.append(f"removed unknown tool: {step.tool}")
            continue
        if any(_key_matches(step, k) for k in playbook["forbidden"]):
            flags.append(f"removed forbidden step for {request_type}: {step.key()}")
            continue
        if step.tool == "draft_reply" and not any(
                _key_matches(step, k) for k in
                playbook["mandatory"] + playbook["optional"]):
            # a draft style that belongs to another branch (e.g. kb_answer in a
            # complaint plan) — replace later via mandatory insertion
            flags.append(f"removed off-playbook draft style: {step.key()}")
            continue
        if any(_key_matches(step, prev.key()) or step.key() == prev.key()
               for prev in kept):
            flags.append(f"removed duplicate step: {step.key()}")
            continue
        kept.append(step)

    for key in playbook["mandatory"]:
        if not any(_key_matches(s, key) for s in kept):
            kept.append(_step_from_key(key, "mandatory step enforced by policy",
                                       "guardrail_repair"))
            flags.append(f"repaired: inserted mandatory step {key}")

    # Ordering: stable sort against the canonical playbook sequence. This also
    # satisfies the hard constraints (lookup_kb before kb_answer, extract_details
    # before route_department, hold_for_human first, mark_resolved last).
    canonical = playbook["mandatory"] + playbook["optional"]
    ordered = sorted(kept, key=lambda s: _canonical_index(s, canonical))
    if [s.key() for s in ordered] != [s.key() for s in kept]:
        flags.append("reordered steps to satisfy policy ordering")

    if len(ordered) > MAX_PLAN_STEPS:
        dropped = ordered[MAX_PLAN_STEPS:]
        mandatory_dropped = [s for s in dropped
                             if any(_key_matches(s, k) for k in playbook["mandatory"])]
        optional_kept = [s for s in ordered[:MAX_PLAN_STEPS]
                         if not any(_key_matches(s, k) for k in playbook["mandatory"])]
        # never drop a mandatory step to satisfy the cap — drop optional ones instead
        for extra in mandatory_dropped:
            if optional_kept:
                victim = optional_kept.pop()
                ordered.remove(victim)
                flags.append(f"dropped optional step over plan cap: {victim.key()}")
        ordered = ordered[:MAX_PLAN_STEPS] + [s for s in mandatory_dropped
                                              if s in ordered[MAX_PLAN_STEPS:]]
        ordered = ordered[:MAX_PLAN_STEPS]
        flags.append(f"capped plan at {MAX_PLAN_STEPS} steps")

    return ordered, flags


def default_plan(request_type: str, reason: str = "default playbook") -> list[PlannedStep]:
    """Mandatory steps only — used by the offline fallback and human review."""
    return [_step_from_key(k, reason, "agent") for k in
            PLAYBOOKS[request_type]["mandatory"]]


def playbook_prompt_text() -> str:
    lines = []
    for rtype, pb in PLAYBOOKS.items():
        lines.append(f'For "{rtype}": mandatory = [{", ".join(pb["mandatory"])}]; '
                     f'optional = [{", ".join(pb["optional"])}]; '
                     f'forbidden = [{", ".join(pb["forbidden"])}].')
    return "\n".join(lines)


def tool_catalog_text() -> str:
    return "\n".join(f"- {name}: {desc}" for name, desc in
                     config.TOOL_DESCRIPTIONS.items())
