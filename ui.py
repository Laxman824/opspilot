"""Presentation layer: CSS, badges, cards, and charts for the OpsPilot UI.

Palette: validated reference instance from the dataviz method — categorical blue
#2a78d6 as the single accent, fixed status palette (good/warning/serious/critical),
ordinal blue ramp for urgency magnitude. Text always wears ink tokens, never the
series color.
"""
from __future__ import annotations

import html

import altair as alt
import pandas as pd
import streamlit as st

# ---------------------------------------------------------------- tokens

INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
BASELINE = "#c3c2b7"
SURFACE = "#fcfcfb"
PLANE = "#f9f9f7"
ACCENT = "#2a78d6"

# status roles (fixed, never themed) — (badge tint bg, badge text ink, dot)
_STATUS_STYLE = {
    "good":     ("rgba(12,163,12,0.12)",  "#006300", "#0ca30c"),
    "info":     ("rgba(42,120,214,0.12)", "#1c5cab", "#2a78d6"),
    "warning":  ("rgba(250,178,25,0.16)", "#7a5200", "#b97e00"),
    "serious":  ("rgba(236,131,90,0.16)", "#8f3d17", "#c9612f"),
    "critical": ("rgba(208,59,59,0.12)",  "#a02c2c", "#d03b3b"),
    "neutral":  ("rgba(11,11,11,0.06)",   "#52514e", "#898781"),
    "violet":   ("rgba(74,58,167,0.10)",  "#4a3aa7", "#4a3aa7"),
}

URGENCY_ROLE = {"Low": "good", "Medium": "info", "High": "serious",
                "Critical": "critical"}
STATUS_ROLE = {
    "PENDING_REVIEW": "warning", "IN_PROGRESS": "info", "RESOLVED": "good",
    "ROUTED": "violet", "ESCALATED": "serious", "HELD_FOR_HUMAN": "critical",
    "NEEDS_ATTENTION": "critical",
}
STATUS_ICON = {
    "PENDING_REVIEW": "⏸", "IN_PROGRESS": "◐", "RESOLVED": "✓", "ROUTED": "➜",
    "ESCALATED": "▲", "HELD_FOR_HUMAN": "⛔", "NEEDS_ATTENTION": "⚠",
}
TYPE_ICON = {"Complaint": "😤", "General Enquiry": "❓", "Service Request": "🔧",
             "Escalation/Urgent": "🚨"}
SOURCE_LABEL = {"gemini": "🤖 Gemini", "keyword_fallback": "🧭 offline fallback",
                "human_override": "👤 human override"}
ORIGIN_STYLE = {"agent": ("🤖", "agent", "info"),
                "guardrail_repair": ("🛡", "guardrail", "warning"),
                "human": ("👤", "human", "violet")}

# ---------------------------------------------------------------- css

_CSS = """
<style>
/* ---------- global chrome ---------- */
#MainMenu, footer, [data-testid="stToolbar"] {visibility: hidden; height: 0;}
.block-container {padding-top: 1.2rem; padding-bottom: 3rem; max-width: 1200px;}
html, body, [class*="css"] {
  font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
}
h1, h2, h3, h4 {letter-spacing: -0.01em;}

/* ---------- tabs ---------- */
.stTabs [data-baseweb="tab-list"] {
  gap: 4px; border-bottom: 1px solid #e1e0d9; padding-bottom: 0;
}
.stTabs [data-baseweb="tab"] {
  height: 44px; padding: 0 18px; border-radius: 8px 8px 0 0;
  font-weight: 600; font-size: 0.92rem; color: #52514e;
}
.stTabs [aria-selected="true"] {
  color: #1c5cab; background: rgba(42,120,214,0.07);
}

/* ---------- hero header ---------- */
.op-hero {
  background: linear-gradient(120deg, #0d366b 0%, #1c5cab 55%, #2a78d6 100%);
  border-radius: 14px; padding: 22px 28px; margin-bottom: 6px; color: #fff;
}
.op-hero h1 {color: #fff; font-size: 1.55rem; margin: 0 0 2px 0; letter-spacing: -0.02em;}
.op-hero p {color: rgba(255,255,255,0.85); margin: 0; font-size: 0.92rem;}
.op-hero .chips {margin-top: 12px;}
.op-hero .chip {
  display: inline-block; background: rgba(255,255,255,0.14);
  border: 1px solid rgba(255,255,255,0.25); color: #fff;
  border-radius: 999px; padding: 3px 12px; font-size: 0.76rem; font-weight: 600;
  margin-right: 8px;
}

/* ---------- pills / badges ---------- */
.op-pill {
  display: inline-flex; align-items: center; gap: 6px;
  border-radius: 999px; padding: 3px 11px;
  font-size: 0.78rem; font-weight: 600; line-height: 1.3;
  border: 1px solid rgba(11,11,11,0.08); white-space: nowrap;
}
.op-dot {width: 7px; height: 7px; border-radius: 50%; display: inline-block;}

/* ---------- cards ---------- */
.op-card {
  background: #fcfcfb; border: 1px solid rgba(11,11,11,0.10);
  border-radius: 12px; padding: 18px 20px; margin-bottom: 14px;
  box-shadow: 0 1px 2px rgba(11,11,11,0.04);
}
.op-card .op-card-title {
  font-size: 0.74rem; font-weight: 700; text-transform: uppercase;
  letter-spacing: 0.08em; color: #898781; margin-bottom: 10px;
}
.op-rationale {color: #0b0b0b; font-size: 0.92rem; margin-top: 10px; line-height: 1.5;}
.op-note {
  background: rgba(42,120,214,0.06); border-left: 3px solid #2a78d6;
  border-radius: 0 8px 8px 0; padding: 10px 14px; margin-top: 10px;
  font-size: 0.86rem; color: #52514e;
}
.op-note.mem {background: rgba(74,58,167,0.06); border-left-color: #4a3aa7;}

/* ---------- confidence meter ---------- */
.op-meter {background: #e1e0d9; border-radius: 999px; height: 8px; margin-top: 12px;}
.op-meter > div {height: 8px; border-radius: 999px;}
.op-meter-label {font-size: 0.78rem; color: #898781; margin-top: 4px;}

/* ---------- plan table ---------- */
table.op-plan {width: 100%; border-collapse: collapse; font-size: 0.88rem;}
table.op-plan th {
  text-align: left; font-size: 0.72rem; text-transform: uppercase;
  letter-spacing: 0.07em; color: #898781; font-weight: 700;
  border-bottom: 1px solid #e1e0d9; padding: 6px 10px;
}
table.op-plan td {
  padding: 9px 10px; border-bottom: 1px solid #efeee9; vertical-align: top;
  color: #0b0b0b;
}
table.op-plan tr:last-child td {border-bottom: none;}
table.op-plan code {
  background: rgba(42,120,214,0.08); color: #1c5cab; border-radius: 6px;
  padding: 2px 8px; font-size: 0.82rem; font-weight: 600;
}
table.op-plan .reason {color: #52514e;}

/* ---------- draft block ---------- */
.op-draft {
  background: #fcfcfb; border: 1px solid rgba(11,11,11,0.10);
  border-left: 3px solid #2a78d6; border-radius: 8px;
  padding: 14px 16px; font-size: 0.9rem; color: #0b0b0b;
  white-space: pre-wrap; line-height: 1.55;
}
.op-draft-meta {font-size: 0.76rem; color: #898781; margin-bottom: 6px;}

/* ---------- stat tiles ---------- */
.op-tile {
  background: #fcfcfb; border: 1px solid rgba(11,11,11,0.10);
  border-radius: 12px; padding: 14px 16px; box-shadow: 0 1px 2px rgba(11,11,11,0.04);
}
.op-tile .v {font-size: 1.7rem; font-weight: 700; color: #0b0b0b; letter-spacing: -0.02em;}
.op-tile .k {
  font-size: 0.72rem; font-weight: 700; text-transform: uppercase;
  letter-spacing: 0.07em; color: #898781; margin-top: 2px;
}

/* ---------- guardrail flags ---------- */
.op-flag {
  display: flex; gap: 8px; align-items: flex-start;
  background: rgba(250,178,25,0.10); border: 1px solid rgba(185,126,0,0.25);
  border-radius: 8px; padding: 8px 12px; margin-top: 8px;
  font-size: 0.84rem; color: #7a5200;
}
.op-flag.ok {
  background: rgba(12,163,12,0.07); border-color: rgba(0,99,0,0.2); color: #006300;
}

/* ---------- expanders ---------- */
div[data-testid="stExpander"] {
  border: 1px solid rgba(11,11,11,0.10); border-radius: 10px;
  background: #fcfcfb; margin-bottom: 8px;
}
div[data-testid="stExpander"] summary {font-weight: 600; font-size: 0.9rem;}

/* ---------- sidebar ---------- */
section[data-testid="stSidebar"] {
  background: #fcfcfb; border-right: 1px solid #e1e0d9;
}
section[data-testid="stSidebar"] .block-container {padding-top: 1.4rem;}
</style>
"""


def inject_css() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------- atoms

def pill(text: str, role: str = "neutral", icon: str = "", dot: bool = True) -> str:
    bg, ink, dot_color = _STATUS_STYLE.get(role, _STATUS_STYLE["neutral"])
    dot_html = (f'<span class="op-dot" style="background:{dot_color}"></span>'
                if dot and not icon else "")
    icon_html = f"{icon} " if icon else ""
    return (f'<span class="op-pill" style="background:{bg};color:{ink}">'
            f'{dot_html}{icon_html}{html.escape(str(text))}</span>')


def urgency_pill(urgency: str) -> str:
    return pill(urgency, URGENCY_ROLE.get(urgency, "neutral"))


def status_pill(status: str) -> str:
    status = str(status).replace("CaseStatus.", "")
    return pill(status.replace("_", " "), STATUS_ROLE.get(status, "neutral"),
                icon=STATUS_ICON.get(status, ""))


def type_chip(request_type: str) -> str:
    return (f'<span style="font-weight:700;font-size:1.02rem;color:{INK}">'
            f'{TYPE_ICON.get(request_type, "📄")} {html.escape(request_type)}</span>')


def card(title: str, body_html: str) -> None:
    st.markdown(f'<div class="op-card"><div class="op-card-title">{title}</div>'
                f'{body_html}</div>', unsafe_allow_html=True)


def hero(api_ok: bool, autonomy_mode: str, critic_enabled: bool) -> None:
    api_chip = "✅ Gemini connected" if api_ok else "🔌 offline fallback mode"
    critic_chip = "🪞 critic on" if critic_enabled else "🪞 critic off"
    st.markdown(
        f"""<div class="op-hero">
        <h1>🛰️ OpsPilot</h1>
        <p>Agentic request triage &amp; remediation — the agent plans, policy guards,
        humans stay in the loop.</p>
        <div class="chips">
          <span class="chip">{api_chip}</span>
          <span class="chip">🎚 {html.escape(autonomy_mode)}</span>
          <span class="chip">{critic_chip}</span>
        </div></div>""",
        unsafe_allow_html=True)


def confidence_meter(confidence: float, threshold: float) -> str:
    pct = max(0.0, min(confidence, 1.0)) * 100
    color = "#0ca30c" if confidence >= threshold else "#b97e00"
    return (f'<div class="op-meter"><div style="width:{pct:.0f}%;'
            f'background:{color}"></div></div>'
            f'<div class="op-meter-label">confidence {confidence:.2f} · '
            f'auto-processing threshold {threshold:.2f}</div>')


def plan_table(rows: list[dict]) -> str:
    """rows: [{key, reason, origin}]"""
    body = ""
    for i, row in enumerate(rows):
        icon, label, role = ORIGIN_STYLE.get(row["origin"],
                                             ("•", row["origin"], "neutral"))
        body += (f'<tr><td style="color:{MUTED}">{i + 1}</td>'
                 f'<td><code>{html.escape(row["key"])}</code></td>'
                 f'<td class="reason">{html.escape(row["reason"])}</td>'
                 f'<td>{pill(label, role, icon=icon)}</td></tr>')
    return ('<table class="op-plan"><thead><tr><th>#</th><th>Tool</th>'
            '<th>Agent\'s justification</th><th>Origin</th></tr></thead>'
            f'<tbody>{body}</tbody></table>')


def draft_block(text: str, meta: str = "") -> None:
    meta_html = f'<div class="op-draft-meta">{html.escape(meta)}</div>' if meta else ""
    st.markdown(f'{meta_html}<div class="op-draft">{html.escape(text)}</div>',
                unsafe_allow_html=True)


def flag(text: str, ok: bool = False) -> None:
    icon = "✓" if ok else "🛡"
    cls = "op-flag ok" if ok else "op-flag"
    st.markdown(f'<div class="{cls}"><span>{icon}</span>'
                f'<span>{html.escape(text)}</span></div>', unsafe_allow_html=True)


def stat_tile(col, value, label: str) -> None:
    col.markdown(f'<div class="op-tile"><div class="v">{value}</div>'
                 f'<div class="k">{html.escape(label)}</div></div>',
                 unsafe_allow_html=True)


# ---------------------------------------------------------------- charts

_AXIS = dict(labelColor=MUTED, titleColor=MUTED, gridColor=GRID,
             domainColor=BASELINE, tickColor=BASELINE, labelFontSize=12,
             titleFontSize=12)


def _base_bar(df: pd.DataFrame, cat_col: str, sort: list[str] | str) -> alt.Chart:
    return alt.Chart(df).mark_bar(
        size=22, cornerRadiusTopRight=4, cornerRadiusBottomRight=4,
    ).encode(
        y=alt.Y(f"{cat_col}:N", sort=sort, title=None,
                axis=alt.Axis(grid=False, labelLimit=180)),
        x=alt.X("count:Q", title=None,
                axis=alt.Axis(tickMinStep=1, format="d", grid=True)),
        tooltip=[alt.Tooltip(f"{cat_col}:N", title=cat_col),
                 alt.Tooltip("count:Q", title="cases", format="d")],
    )


def _labels(chart: alt.Chart) -> alt.Chart:
    return chart.mark_text(align="left", dx=6, color=INK_2, fontSize=12,
                           fontWeight=600).encode(text=alt.Text("count:Q",
                                                                format="d"))


def _finish(chart: alt.Chart, height: int = 190) -> alt.Chart:
    return chart.properties(height=height, background="transparent").configure_axis(
        **_AXIS).configure_view(stroke=None)


def volume_by_type_chart(counts: pd.Series) -> alt.Chart:
    """Single measure across named categories → one hue; identity lives on the axis."""
    df = counts.rename_axis("type").reset_index(name="count")
    order = [t for t in TYPE_ICON if t in set(df["type"])]
    base = _base_bar(df, "type", order).encode(color=alt.value(ACCENT))
    return _finish(base + _labels(base))


_STATUS_COLOR_SCALE = {  # status palette — state, never a series
    "PENDING_REVIEW": "#b97e00", "IN_PROGRESS": "#2a78d6", "RESOLVED": "#0ca30c",
    "ROUTED": "#4a3aa7", "ESCALATED": "#c9612f", "HELD_FOR_HUMAN": "#d03b3b",
    "NEEDS_ATTENTION": "#d03b3b",
}


def status_chart(counts: pd.Series) -> alt.Chart:
    df = counts.rename_axis("status").reset_index(name="count")
    order = [s for s in STATUS_ROLE if s in set(df["status"])]
    base = _base_bar(df, "status", order).encode(
        color=alt.Color("status:N", legend=None, scale=alt.Scale(
            domain=list(_STATUS_COLOR_SCALE), range=list(
                _STATUS_COLOR_SCALE.values()))))
    return _finish(base + _labels(base))


_URGENCY_RAMP = {  # ordinal blue ramp, validated (light surface, --ordinal)
    "Low": "#86b6ef", "Medium": "#5598e7", "High": "#2a78d6", "Critical": "#184f95",
}


def urgency_chart(counts: pd.Series) -> alt.Chart:
    df = counts.rename_axis("urgency").reset_index(name="count")
    base = _base_bar(df, "urgency", list(_URGENCY_RAMP)).encode(
        color=alt.Color("urgency:N", legend=None, scale=alt.Scale(
            domain=list(_URGENCY_RAMP), range=list(_URGENCY_RAMP.values()))))
    return _finish(base + _labels(base))
