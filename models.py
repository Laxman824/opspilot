"""Dataclasses and enums shared across OpsPilot."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class CaseStatus(str, Enum):
    RECEIVED = "RECEIVED"
    PENDING_REVIEW = "PENDING_REVIEW"  # awaiting human (low confidence / propose & confirm)
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"
    ROUTED = "ROUTED"
    ESCALATED = "ESCALATED"
    HELD_FOR_HUMAN = "HELD_FOR_HUMAN"
    NEEDS_ATTENTION = "NEEDS_ATTENTION"  # a tool failed mid-plan


def new_request_id() -> str:
    return "REQ-" + uuid.uuid4().hex[:6]


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


@dataclass
class IncomingRequest:
    id: str
    channel: str  # "form" | "inbox" | "batch"
    sender: str
    subject: str
    body: str
    received_at: str


@dataclass
class Classification:
    request_type: str
    urgency: str
    confidence: float
    rationale: str
    sentiment: str
    suggested_department: str
    source: str = "gemini"  # gemini | keyword_fallback | human_override


@dataclass
class PlannedStep:
    tool: str
    reason: str
    params: dict = field(default_factory=dict)
    origin: str = "agent"  # agent | guardrail_repair | human

    def key(self) -> str:
        """Playbook identity: draft_reply is distinguished by style."""
        if self.tool == "draft_reply" and self.params.get("style"):
            return f"draft_reply:{self.params['style']}"
        return self.tool


@dataclass
class ToolResult:
    tool: str
    status: str  # SUCCESS | FAILED | SKIPPED
    artifact: dict
    executed_at: str


@dataclass
class AgentRun:
    request: IncomingRequest
    classification: Classification
    memory_note: str
    memory_impact: str
    proposed_plan: list[PlannedStep]
    final_plan: list[PlannedStep]
    guardrail_flags: list[str]
    results: list[ToolResult]
    critic: dict | None
    final_status: str
