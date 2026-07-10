"""Central configuration for OpsPilot."""
import os

from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
if not GEMINI_API_KEY:
    # Streamlit Cloud deployments provide the key via st.secrets instead of .env
    try:
        import streamlit as st

        GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY", "")
    except Exception:
        GEMINI_API_KEY = ""

PRIMARY_MODEL = "gemini-2.5-flash"
FALLBACK_MODEL = "gemini-2.5-flash-lite"
MAX_RETRIES = 3
RETRY_BASE_DELAY = 2.0  # seconds; backoff 2s, 4s, 8s on 429/5xx

CONFIDENCE_THRESHOLD = 0.70
BATCH_THROTTLE_SECONDS = 7.0  # keeps ~4 calls/request under the 10 RPM free tier
CRITIC_ENABLED_DEFAULT = True
DB_PATH = os.path.join(os.path.dirname(__file__), "opspilot.db")
MEMORY_WINDOW_DAYS = 30

REQUEST_TYPES = ["Complaint", "General Enquiry", "Service Request", "Escalation/Urgent"]
URGENCY_LEVELS = ["Low", "Medium", "High", "Critical"]
SENTIMENTS = ["calm", "frustrated", "angry", "distressed"]
AUTONOMY_MODES = ["Review low-confidence only", "Full auto", "Propose & confirm"]

DEPARTMENTS = {
    "Billing": "billing-team@demo-ops.example",
    "Technical Support": "techsupport@demo-ops.example",
    "Account Management": "accounts@demo-ops.example",
    "Field Services": "field-services@demo-ops.example",
    "General Operations": "ops@demo-ops.example",
}
SENIOR_HANDLER = "senior-handler@demo-ops.example"
SUPERVISOR = "supervisor@demo-ops.example"
SLA_HOURS = {"Low": 72, "Medium": 24, "High": 4, "Critical": 1}

# Tool catalog metadata. tools.py binds implementations to these names; keeping the
# metadata here lets gemini_client build the planner prompt without importing tools
# (which itself imports gemini_client).
TOOL_DESCRIPTIONS = {
    "draft_reply": (
        'params: {"style": "ack_empathetic" | "ack_urgent" | "kb_answer" | "confirmation"} — '
        "generate a customer-facing draft: empathetic complaint acknowledgement, urgent "
        "de-escalating acknowledgement, knowledge-base-grounded answer, or service confirmation."
    ),
    "lookup_kb": "params: {} — find the relevant knowledge-base section for an enquiry (run before draft_reply kb_answer).",
    "extract_details": "params: {} — extract structured service-request fields (service, account ref, action, timing).",
    "route_department": 'params: {"department": "<name>"} (optional) — route the case to a department team.',
    "escalate_case": "params: {} — escalate the case to the senior handler.",
    "notify_supervisor": 'params: {"reason": "<why>"} — alert the supervisor (repeat complainant, churn risk, critical case).',
    "log_priority": "params: {} — flag the case as priority in the case log.",
    "schedule_follow_up": 'params: {"hours": <int>} — set a follow-up reminder N hours from now (default 2).',
    "set_sla": "params: {} — start the SLA timer based on urgency.",
    "hold_for_human": 'params: {"reason": "<why>"} — pause auto-resolution; a human must take over.',
    "send_response": "params: {} — send the latest draft to the requester (simulated).",
    "mark_resolved": "params: {} — close the case as auto-resolved.",
}
TOOL_NAMES = list(TOOL_DESCRIPTIONS.keys())

KNOWLEDGE_BASE = {
    "billing": (
        "Invoices are issued on the 1st of each month. Payments accepted via card, "
        "bank transfer, and UPI. Late fee of 2% applies after a 10-day grace period. "
        "Refunds are processed within 5-7 business days."
    ),
    "account": (
        "Password resets are self-service via the portal 'Forgot Password' link. "
        "Account details can be updated under Settings > Profile. Account closure "
        "requires an email from the registered address."
    ),
    "services": (
        "Support hours: Mon-Sat 8am-8pm IST. Standard installation lead time is "
        "3 business days. Service upgrades take effect from the next billing cycle. "
        "Coverage/outage status is at status.demo-ops.example."
    ),
    "general": (
        "We are a customer operations desk handling billing, technical support, "
        "account management, and field service scheduling."
    ),
}
