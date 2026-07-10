"""The agent loop: perceive -> plan -> guard -> gate -> act -> reflect -> record."""
from __future__ import annotations

import json

import config
import db
import gemini_client
import guardrails
import memory
import tools
from models import (AgentRun, CaseStatus, Classification, IncomingRequest,
                    PlannedStep, ToolResult, now_iso)


def _execute_plan(req: IncomingRequest, cls: Classification,
                  plan: list[PlannedStep]) -> tuple[list[ToolResult], dict]:
    results: list[ToolResult] = []
    ctx: dict = {}
    failed = False
    for step in plan:
        if failed:
            results.append(ToolResult(tool=step.tool, status="SKIPPED",
                                      artifact={"skipped_because": "earlier step failed"},
                                      executed_at=now_iso()))
            continue
        try:
            result = tools.TOOL_REGISTRY[step.tool](req, cls, step.params, ctx)
        except Exception as e:  # noqa: BLE001 — a tool bug must never crash the run
            result = ToolResult(tool=step.tool, status="FAILED",
                                artifact={"error": str(e)}, executed_at=now_iso())
        if result.status == "FAILED":
            failed = True
        results.append(result)
    return results, ctx


def _reflect(req: IncomingRequest, results: list[ToolResult],
             ctx: dict) -> dict | None:
    """Critic pass over the last customer-facing draft; revise in place if rejected."""
    style = ctx.get("last_draft_style")
    drafts = ctx.get("draft_texts", {})
    if not style or style not in drafts:
        return None
    verdict = gemini_client.critique_draft(drafts[style], req.body, style)
    verdict["style"] = style
    verdict["original_text"] = drafts[style]
    if not verdict["approved"] and verdict["revised_text"]:
        for result in results:
            if (result.tool in ("draft_reply", "send_response")
                    and result.status == "SUCCESS"
                    and result.artifact.get("style", style) == style):
                key = "draft_text" if result.tool == "draft_reply" else "text"
                if key in result.artifact:
                    result.artifact[key] = verdict["revised_text"]
                    result.artifact["revised_by_critic"] = True
        verdict["revised"] = True
    else:
        verdict["revised"] = False
    return verdict


def process_request(req: IncomingRequest,
                    autonomy_mode: str = "Review low-confidence only",
                    critic_enabled: bool = True,
                    human_cls: Classification | None = None,
                    human_plan: list[PlannedStep] | None = None) -> AgentRun:
    """Run the full agent loop for one request.

    human_cls/human_plan come from the Human Review tab: they replace the
    planning step (source=human_override) and bypass the autonomy gate.
    """
    # 1. PERCEIVE — recall sender history BEFORE this case is written to the DB
    history = memory.get_sender_history(req.sender)
    memory_note = history["note"]

    # 2. PLAN (or accept the human's decision)
    if human_cls is not None:
        cls = human_cls
        proposed = human_plan or guardrails.default_plan(
            cls.request_type, "human-approved playbook")
        memory_impact = "human decision"
    else:
        cls, proposed, memory_impact = gemini_client.plan_request(req, memory_note)

    # 3. GUARD — repair the plan to policy before anything executes
    final_plan, flags = guardrails.validate_and_repair_plan(proposed, cls.request_type)

    # 4. GATE — decide whether a human must approve first
    needs_human = human_cls is None and (
        cls.confidence < config.CONFIDENCE_THRESHOLD
        or autonomy_mode == "Propose & confirm")
    if autonomy_mode == "Full auto" and cls.source != "keyword_fallback":
        needs_human = False

    db.upsert_case(req, cls,
                   CaseStatus.PENDING_REVIEW if needs_human else CaseStatus.IN_PROGRESS,
                   memory_note=memory_note, guardrail_flags=flags)
    db.insert_plan(req.id, "proposed", proposed)
    db.insert_plan(req.id, "final", final_plan)

    if needs_human:
        return AgentRun(request=req, classification=cls, memory_note=memory_note,
                        memory_impact=memory_impact, proposed_plan=proposed,
                        final_plan=final_plan, guardrail_flags=flags, results=[],
                        critic=None, final_status=CaseStatus.PENDING_REVIEW)

    # 5. ACT
    results, ctx = _execute_plan(req, cls, final_plan)

    # 6. REFLECT
    critic = _reflect(req, results, ctx) if critic_enabled else None
    if critic and critic["revised"]:
        flags = flags + ["revised_by_critic"]

    # 7. RECORD
    for result in results:
        db.insert_result(req.id, result)
    if any(r.status == "FAILED" for r in results):
        final_status = CaseStatus.NEEDS_ATTENTION
    else:
        final_status = guardrails.PLAYBOOKS[cls.request_type]["terminal_status"]
    db.update_case(req.id, status=final_status,
                   follow_up_at=ctx.get("follow_up_at"),
                   guardrail_flags=json.dumps(flags))
    if critic:
        db.insert_result(req.id, ToolResult(
            tool="critic_review",
            status="SUCCESS" if critic["available"] else "SKIPPED",
            artifact={k: critic[k] for k in
                      ("approved", "issues", "revised", "style") if k in critic},
            executed_at=now_iso()))

    return AgentRun(request=req, classification=cls, memory_note=memory_note,
                    memory_impact=memory_impact, proposed_plan=proposed,
                    final_plan=final_plan, guardrail_flags=flags, results=results,
                    critic=critic, final_status=final_status)
