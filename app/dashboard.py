"""Revenue Intelligence Agent - Streamlit dashboard.

Interactive front end. Reads the generated revenue CSV and the pre-generated
narrative cache; renders KPIs, charts, a status table, and the AI commentary.

The deployed (public) app needs no API key: narratives come from the committed
cache. When an ANTHROPIC_API_KEY is available locally, an optional
"Regenerate live" control appears for on-the-fly generation.

Design language: light "fintech SaaS" - off-white canvas, white cards with soft
shadows, a deep-navy hero band, Inter typography, tabular figures, and color used
only where it carries meaning (variance direction, status).

Run:
    streamlit run app/dashboard.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from analysis.variance_engine import (  # noqa: E402
    STATUS_DEFINITIONS,
    STATUS_ORDER,
    calculate_variance,
)

CSV_PATH = ROOT / "data" / "revenue_data.csv"
CACHE_PATH = ROOT / "data" / "narratives_cache.json"

# --------------------------------------------------------------------------- #
# Design tokens
# --------------------------------------------------------------------------- #
INK = "#0F172A"          # slate-900, primary text / hero band
INK_SOFT = "#475569"     # slate-600, secondary text
MUTED = "#94A3B8"        # slate-400, labels
LINE = "#E2E8F0"         # slate-200, borders
CANVAS = "#F1F5F9"       # slate-100, app background
ACCENT = "#2563EB"       # blue-600, brand accent / actuals
PLAN_GRAY = "#CBD5E1"    # slate-300, plan bars

POS = "#16A34A"          # green-600
NEG = "#DC2626"          # red-600
WARN = "#D97706"         # amber-600

# Colors live here (presentation), keyed by the engine's canonical status labels.
# "Ahead of Plan" gets a distinct indigo (not the brand blue used for Actuals) and
# "Favorable" a teal, so beating-plan states read as positive without colliding
# with the chart's Actuals color or with On Track's green.
STATUS_META = {
    "Ahead of Plan": {"color": "#4F46E5", "bg": "#EEF2FF", "fg": "#3730A3"},  # indigo
    "Favorable": {"color": "#0D9488", "bg": "#CCFBF1", "fg": "#115E59"},      # teal
    "On Track": {"color": POS, "bg": "#DCFCE7", "fg": "#166534"},             # green
    "At Risk": {"color": WARN, "bg": "#FEF3C7", "fg": "#92400E"},             # amber
    "Critical": {"color": NEG, "bg": "#FEE2E2", "fg": "#991B1B"},             # red
}

# Fail loudly at import if a status bucket has no color, rather than silently
# falling back (which could render a Critical line as green and hide the bug).
_missing = set(STATUS_ORDER) - set(STATUS_META)
if _missing:
    raise RuntimeError(f"STATUS_META is missing colors for: {sorted(_missing)}")

# Per-line palette for the trend chart.
LINE_PALETTE = {
    "Enterprise": "#2563EB",
    "SMB": "#16A34A",
    "API": "#D97706",
    "Consulting": "#9333EA",
}

st.set_page_config(
    page_title="Revenue Intelligence Agent",
    page_icon="\U0001F4C8",
    layout="wide",
    initial_sidebar_state="expanded",
)


# --------------------------------------------------------------------------- #
# Global styling
# --------------------------------------------------------------------------- #
def inject_css() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

        html, body, [class*="css"], .stApp { font-family: 'Inter', -apple-system, sans-serif; }
        .stApp { background: #F1F5F9; }

        /* Hide default Streamlit chrome for a product-grade look. Keep the header
           itself (it hosts the sidebar collapse/expand toggle) but make it blend
           in, so a collapsed sidebar can always be reopened. */
        #MainMenu, footer { visibility: hidden; height: 0; }
        header[data-testid="stHeader"] { background: transparent; }
        /* Hide the toolbar's right-side clutter (Deploy button, main menu) and the
           colored bar - but DON'T hide the whole toolbar: it also contains the
           sidebar expand button, so blanking it leaves no way to reopen a
           collapsed sidebar. */
        [data-testid="stToolbarActions"], [data-testid="stAppDeployButton"],
        [data-testid="stDecoration"] { display: none; }
        /* When the sidebar is collapsed, this expand control (the button itself)
           sits at the top-left over the dark hero band. Style it as a visible
           white pill with a dark icon and high z-index so it can always be found
           and clicked. */
        [data-testid="stExpandSidebarButton"] {
            background: #ffffff !important; z-index: 1000;
            border: 1px solid #E2E8F0; border-radius: 9px;
            box-shadow: 0 2px 10px rgba(15,23,42,0.22);
        }
        [data-testid="stExpandSidebarButton"] span { color: #0F172A !important; }
        .block-container { padding: 1.4rem 2.6rem 4rem 2.6rem; max-width: 1320px; }

        /* Tabular, lining figures for money */
        .num { font-variant-numeric: tabular-nums; font-feature-settings: "tnum"; }

        /* ---------- Hero band ---------- */
        .hero {
            display: flex; align-items: center; justify-content: space-between;
            background: linear-gradient(120deg, #0F172A 0%, #1E293B 60%, #1E3A8A 100%);
            border-radius: 16px; padding: 22px 28px; margin-bottom: 22px;
            box-shadow: 0 10px 30px -12px rgba(15,23,42,0.45);
        }
        .hero-left { display: flex; align-items: center; gap: 16px; }
        .hero-mark {
            width: 46px; height: 46px; border-radius: 12px;
            background: linear-gradient(135deg, #3B82F6, #2563EB);
            display: flex; align-items: center; justify-content: center;
            box-shadow: 0 6px 16px -4px rgba(37,99,235,0.6);
        }
        .hero-title { color: #fff; font-size: 1.42rem; font-weight: 800; letter-spacing: -0.02em; line-height: 1.15; }
        .hero-sub { color: #94A3B8; font-size: 0.86rem; font-weight: 500; margin-top: 2px; }
        .hero-right { display: flex; align-items: center; gap: 22px; }
        .hero-week { text-align: right; }
        .hero-week .lbl { color: #64748B; font-size: 0.66rem; font-weight: 700; letter-spacing: 0.12em; }
        .hero-week .val { color: #E2E8F0; font-size: 1.0rem; font-weight: 700; }
        .hero-badge {
            font-size: 0.8rem; font-weight: 700; padding: 8px 16px; border-radius: 999px;
            display: inline-flex; align-items: center; gap: 8px; color: #fff;
        }
        .hero-badge .dot { width: 8px; height: 8px; border-radius: 50%; background: #fff; }

        /* ---------- KPI cards ---------- */
        .kpi-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 8px; }
        .kpi {
            background: #fff; border: 1px solid #E2E8F0; border-radius: 14px; padding: 18px 20px;
            box-shadow: 0 1px 2px rgba(15,23,42,0.04); position: relative; overflow: hidden;
        }
        .kpi::before {
            content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 4px;
            background: var(--bar, #2563EB);
        }
        .kpi-lbl { color: #64748B; font-size: 0.7rem; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; }
        .kpi-val { color: #0F172A; font-size: 1.85rem; font-weight: 800; letter-spacing: -0.02em; margin-top: 6px; }
        .kpi-sub { font-size: 0.82rem; font-weight: 600; margin-top: 8px; display: flex; align-items: center; gap: 6px; }
        .kpi-sub.pos { color: #16A34A; }
        .kpi-sub.neg { color: #DC2626; }
        .kpi-sub.neutral { color: #94A3B8; }

        /* ---------- Section labels / panels ---------- */
        .sec-lbl { color: #0F172A; font-size: 1.02rem; font-weight: 700; letter-spacing: -0.01em; margin: 2px 0 2px 0; }
        .sec-hint { color: #94A3B8; font-size: 0.8rem; font-weight: 500; margin-bottom: 10px; }

        /* bordered containers -> cards */
        [data-testid="stVerticalBlockBorderWrapper"] {
            background: #fff; border-radius: 14px; border: 1px solid #E2E8F0 !important;
            box-shadow: 0 1px 2px rgba(15,23,42,0.04); padding: 4px 6px;
        }

        /* ---------- Status table ---------- */
        .stat-wrap { overflow-x: auto; }
        table.stat { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
        table.stat thead th {
            text-align: right; color: #64748B; font-size: 0.7rem; font-weight: 700;
            letter-spacing: 0.06em; text-transform: uppercase; padding: 6px 14px 12px 14px;
            border-bottom: 1px solid #E2E8F0;
        }
        table.stat thead th:first-child { text-align: left; }
        table.stat tbody td { text-align: right; padding: 13px 14px; border-bottom: 1px solid #F1F5F9; color: #334155; }
        table.stat tbody td:first-child { text-align: left; font-weight: 700; color: #0F172A; }
        table.stat tbody tr:last-child td { border-bottom: none; }
        .pill {
            display: inline-block; padding: 4px 12px; border-radius: 999px;
            font-size: 0.74rem; font-weight: 700;
        }
        .var-pos { color: #16A34A; font-weight: 700; }
        .var-neg { color: #DC2626; font-weight: 700; }
        .trend { font-weight: 600; }

        /* ---------- Executive briefing ---------- */
        .ai-head { display: flex; align-items: center; gap: 10px; margin-bottom: 2px; }
        .ai-badge {
            font-size: 0.68rem; font-weight: 700; letter-spacing: 0.04em; color: #4338CA;
            background: #EEF2FF; border: 1px solid #C7D2FE; padding: 4px 10px; border-radius: 999px;
        }
        .brief-summary { color: #1E293B; font-size: 1.0rem; line-height: 1.6; font-weight: 450; }
        .drivers { list-style: none; padding: 0; margin: 6px 0 0 0; }
        .drivers li {
            display: flex; gap: 12px; padding: 11px 0; border-bottom: 1px solid #F1F5F9;
            color: #334155; font-size: 0.92rem; line-height: 1.5;
        }
        .drivers li:last-child { border-bottom: none; }
        .drivers .idx {
            flex: 0 0 24px; height: 24px; border-radius: 7px; background: #EFF6FF; color: #2563EB;
            font-weight: 800; font-size: 0.78rem; display: flex; align-items: center; justify-content: center;
        }
        .risk {
            display: flex; gap: 12px; background: #FFFBEB; border: 1px solid #FDE68A;
            border-left: 4px solid #D97706; border-radius: 10px; padding: 14px 16px; margin-top: 4px;
        }
        .risk .ico { font-size: 1.05rem; }
        .risk .body { color: #78350F; font-size: 0.9rem; line-height: 1.55; }
        .risk .body b { color: #92400E; }

        .anom { display: flex; flex-direction: column; gap: 8px; }
        .anom .chip {
            background: #FEF2F2; border: 1px solid #FECACA; border-left: 3px solid #DC2626;
            color: #991B1B; font-size: 0.84rem; font-weight: 600; line-height: 1.45;
            padding: 9px 12px; border-radius: 8px;
        }
        .recap-row {
            display: flex; align-items: center; justify-content: space-between;
            padding: 9px 0; border-bottom: 1px solid #F1F5F9; font-size: 0.88rem; color: #475569;
        }
        .recap-row:last-child { border-bottom: none; }
        .recap-row .n { font-weight: 800; color: #0F172A; font-variant-numeric: tabular-nums; }
        .recap-clean { color: #16A34A; font-weight: 700; font-size: 0.9rem; margin-bottom: 10px; }

        /* ---------- Sidebar ---------- */
        [data-testid="stSidebar"] { background: #fff; border-right: 1px solid #E2E8F0; }
        [data-testid="stSidebar"] .block-container { padding-top: 1.4rem; }
        .side-brand { font-weight: 800; color: #0F172A; font-size: 1.05rem; letter-spacing: -0.01em; }
        .side-lbl { color: #94A3B8; font-size: 0.7rem; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase; margin: 14px 0 4px 0; }
        .legend-row { display: flex; align-items: center; gap: 9px; font-size: 0.84rem; color: #475569; padding: 3px 0; }
        .legend-row .sw { width: 11px; height: 11px; border-radius: 3px; }

        .foot { color: #94A3B8; font-size: 0.8rem; text-align: center; margin-top: 28px; }
        .foot b { color: #475569; }
        </style>
        """,
        unsafe_allow_html=True,
    )


# --------------------------------------------------------------------------- #
# Data loading
# --------------------------------------------------------------------------- #
@st.cache_data
def load_data() -> pd.DataFrame:
    df = pd.read_csv(CSV_PATH)
    df["week_start_date"] = df["week_start_date"].astype(str)
    return df


@st.cache_data
def load_narrative_cache() -> dict:
    if CACHE_PATH.exists():
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    return {}


def _has_api_key() -> bool:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return True
    try:
        return bool(st.secrets.get("ANTHROPIC_API_KEY"))
    except Exception:
        return False


@st.cache_data(show_spinner=False)
def generate_live_narrative(week: str) -> dict:
    """Call the API live for one week (only used by the gated refresh button)."""
    from ai.narrative_engine import generate_narrative

    df = load_data()
    summary = calculate_variance(df, week=week)
    return generate_narrative(summary)


def _portfolio_wow_pct(df: pd.DataFrame, week: str) -> float | None:
    """Portfolio-level week-over-week change in total actual revenue."""
    weeks = sorted(df["week_start_date"].unique())
    i = weeks.index(week)
    if i == 0:
        return None
    cur = df[df["week_start_date"] == week]["actual_revenue"].sum()
    prev = df[df["week_start_date"] == weeks[i - 1]]["actual_revenue"].sum()
    if not prev:
        return None
    return (cur - prev) / prev * 100.0


# --------------------------------------------------------------------------- #
# Small formatting helpers
# --------------------------------------------------------------------------- #
def money(v: float) -> str:
    return f"${v:,.0f}"


def signed_money(v: float) -> str:
    return f"{'+' if v >= 0 else '-'}${abs(v):,.0f}"


def signed_pct(v: float) -> str:
    return f"{v:+.1f}%"


# --------------------------------------------------------------------------- #
# Charts
# --------------------------------------------------------------------------- #
def _base_layout(**overrides) -> dict:
    layout = dict(
        font=dict(family="Inter, sans-serif", size=13, color=INK_SOFT),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(t=10, b=10, l=10, r=10),
        hoverlabel=dict(font=dict(family="Inter, sans-serif", size=12), bgcolor="white"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
                    font=dict(size=12), title_text=""),
        xaxis=dict(showgrid=False, linecolor=LINE, tickcolor=LINE, color=MUTED),
        yaxis=dict(showgrid=True, gridcolor="#F1F5F9", zeroline=False,
                   tickprefix="$", tickformat=",.0f", color=MUTED),
    )
    layout.update(overrides)
    return layout


def build_bar_chart(summary: dict) -> go.Figure:
    lines = list(summary["product_lines"].keys())
    actual = [summary["product_lines"][l]["actual"] for l in lines]
    plan = [summary["product_lines"][l]["plan"] for l in lines]

    fig = go.Figure()
    fig.add_bar(
        name="Actual", x=lines, y=actual, marker_color=ACCENT, marker_line_width=0,
        hovertemplate="<b>%{x}</b><br>Actual: $%{y:,.0f}<extra></extra>",
    )
    fig.add_bar(
        name="Plan", x=lines, y=plan, marker_color=PLAN_GRAY, marker_line_width=0,
        hovertemplate="<b>%{x}</b><br>Plan: $%{y:,.0f}<extra></extra>",
    )
    fig.update_layout(_base_layout(barmode="group", bargap=0.35, bargroupgap=0.12, height=360))
    return fig


def build_trend_chart(df: pd.DataFrame) -> go.Figure:
    weeks = sorted(df["week_start_date"].unique())
    lines = [l for l in ["Enterprise", "SMB", "API", "Consulting"] if l in set(df["product_line"])]

    fig = go.Figure()
    for line in lines:
        sub = df[df["product_line"] == line].sort_values("week_start_date")
        color = LINE_PALETTE.get(line, ACCENT)
        fig.add_scatter(
            x=sub["week_start_date"], y=sub["actual_revenue"],
            mode="lines+markers", name=line,
            line=dict(color=color, width=2.6), marker=dict(size=5),
            hovertemplate=f"<b>{line}</b><br>%{{x}}<br>Actual: $%{{y:,.0f}}<extra></extra>",
        )
        fig.add_scatter(
            x=sub["week_start_date"], y=sub["plan_revenue"],
            mode="lines", name=f"{line} plan",
            line=dict(color=color, width=1.1, dash="dot"),
            opacity=0.45, showlegend=False, hoverinfo="skip",
        )

    fig.update_layout(_base_layout(height=380))
    return fig


# --------------------------------------------------------------------------- #
# HTML fragments
# --------------------------------------------------------------------------- #
def render_hero(summary: dict) -> None:
    status = summary["portfolio"]["status"]
    meta = STATUS_META[status]
    mark = (
        "<svg width='26' height='26' viewBox='0 0 24 24' fill='none'>"
        "<path d='M4 16 L9 10 L13 13 L20 5' stroke='white' stroke-width='2.4' "
        "stroke-linecap='round' stroke-linejoin='round'/>"
        "<circle cx='20' cy='5' r='2' fill='white'/></svg>"
    )
    st.markdown(
        f"""
        <div class="hero">
          <div class="hero-left">
            <div class="hero-mark">{mark}</div>
            <div>
              <div class="hero-title">Revenue Intelligence Agent</div>
              <div class="hero-sub">Weekly actual-vs-plan variance analysis &middot; AI executive commentary</div>
            </div>
          </div>
          <div class="hero-right">
            <div class="hero-week">
              <div class="lbl">REPORTING WEEK</div>
              <div class="val num">{summary['week']}</div>
            </div>
            <span class="hero-badge" style="background:{meta['color']};">
              <span class="dot"></span>{status}
            </span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_kpis(summary: dict, wow_pct: float | None) -> None:
    p = summary["portfolio"]
    var_pos = p["variance_dollars"] >= 0
    var_color = POS if var_pos else NEG
    status_meta = STATUS_META[p["status"]]

    if wow_pct is None:
        wow_html = '<span class="kpi-sub neutral">First reporting week</span>'
    else:
        cls = "pos" if wow_pct >= 0 else "neg"
        arrow = "▲" if wow_pct >= 0 else "▼"
        wow_html = f'<div class="kpi-sub {cls}">{arrow} {abs(wow_pct):.1f}% vs prior week</div>'

    var_arrow = "▲" if var_pos else "▼"
    var_cls = "pos" if var_pos else "neg"

    st.markdown(
        f"""
        <div class="kpi-grid">
          <div class="kpi" style="--bar:{ACCENT};">
            <div class="kpi-lbl">Total Actual Revenue</div>
            <div class="kpi-val num">{money(p['total_actual'])}</div>
            {wow_html}
          </div>
          <div class="kpi" style="--bar:{PLAN_GRAY};">
            <div class="kpi-lbl">Total Plan Revenue</div>
            <div class="kpi-val num">{money(p['total_plan'])}</div>
            <div class="kpi-sub neutral">Weekly target</div>
          </div>
          <div class="kpi" style="--bar:{var_color};">
            <div class="kpi-lbl">Variance vs Plan</div>
            <div class="kpi-val num" style="color:{var_color};">{signed_money(p['variance_dollars'])}</div>
            <div class="kpi-sub {var_cls}">{var_arrow} {signed_pct(p['variance_pct'])} to plan</div>
          </div>
          <div class="kpi" style="--bar:{status_meta['color']};">
            <div class="kpi-lbl">Portfolio Status</div>
            <div class="kpi-val" style="color:{status_meta['color']};">{p['status']}</div>
            <div class="kpi-sub neutral">{signed_pct(p['variance_pct'])} variance threshold</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_status_table(summary: dict) -> None:
    trend_icons = {
        "Improving": ("▲", POS),
        "Declining": ("▼", NEG),
        "Stable": ("→", MUTED),
    }
    rows = ""
    for name, pl in summary["product_lines"].items():
        meta = STATUS_META[pl["status"]]
        var_cls = "var-pos" if pl["variance_pct"] >= 0 else "var-neg"
        wow_cls = "var-pos" if pl["wow_change_pct"] >= 0 else "var-neg"
        ticon, tcolor = trend_icons.get(pl["trend"], ("→", MUTED))
        rows += f"""
          <tr>
            <td>{name}</td>
            <td class="num">{money(pl['actual'])}</td>
            <td class="num">{money(pl['plan'])}</td>
            <td class="num {var_cls}">{signed_money(pl['variance_dollars'])}</td>
            <td class="num {var_cls}">{signed_pct(pl['variance_pct'])}</td>
            <td class="num {wow_cls}">{signed_pct(pl['wow_change_pct'])}</td>
            <td class="trend" style="color:{tcolor};">{ticon} {pl['trend']}</td>
            <td><span class="pill" style="background:{meta['bg']};color:{meta['fg']};">{pl['status']}</span></td>
          </tr>"""

    st.markdown(
        f"""
        <div class="stat-wrap">
        <table class="stat">
          <thead><tr>
            <th>Product Line</th><th>Actual</th><th>Plan</th>
            <th>Variance $</th><th>Variance %</th><th>WoW</th><th>Trend</th><th>Status</th>
          </tr></thead>
          <tbody>{rows}</tbody>
        </table>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_narrative(narrative: dict) -> None:
    st.markdown(
        '<div class="ai-head"><span class="sec-lbl">Executive Briefing</span>'
        '<span class="ai-badge">✨ Claude Opus 4.8</span></div>'
        '<div class="sec-hint">Generated from this week\'s variance data</div>',
        unsafe_allow_html=True,
    )

    if not narrative or not narrative.get("executive_summary"):
        st.warning("No narrative available for this week.")
        return

    st.markdown(f'<p class="brief-summary">{narrative["executive_summary"]}</p>', unsafe_allow_html=True)

    drivers = narrative.get("top_3_drivers", [])
    if drivers:
        items = "".join(
            f'<li><span class="idx">{i}</span><span>{d}</span></li>'
            for i, d in enumerate(drivers, 1)
        )
        st.markdown('<div class="side-lbl" style="margin-top:14px;">Key Drivers</div>', unsafe_allow_html=True)
        st.markdown(f'<ul class="drivers">{items}</ul>', unsafe_allow_html=True)

    risk = narrative.get("risk_flag", "")
    if risk:
        st.markdown('<div class="side-lbl" style="margin-top:14px;">Risk Flag</div>', unsafe_allow_html=True)
        st.markdown(
            f'<div class="risk"><div class="ico">⚠️</div><div class="body">{risk}</div></div>',
            unsafe_allow_html=True,
        )


def render_signals(summary: dict) -> None:
    """Right-rail panel: flagged anomalies if any, else a clean-week status recap."""
    anomalies = summary.get("anomalies", [])
    section_header("This Week's Signals")

    if anomalies:
        chips = "".join(f'<div class="chip">⚡ {a}</div>' for a in anomalies)
        st.markdown(f'<div class="anom">{chips}</div>', unsafe_allow_html=True)
        return

    # No anomalies: show the status distribution across product lines.
    counts = {label: 0 for label in STATUS_ORDER}
    for pl in summary["product_lines"].values():
        counts[pl["status"]] = counts.get(pl["status"], 0) + 1
    rows = ""
    for label in STATUS_ORDER:
        m = STATUS_META[label]
        rows += (
            f'<div class="recap-row"><span style="display:flex;align-items:center;gap:9px;">'
            f'<span class="sw" style="display:inline-block;width:11px;height:11px;'
            f'border-radius:3px;background:{m["color"]};"></span>{label}</span>'
            f'<span class="n">{counts[label]}</span></div>'
        )
    st.markdown('<div class="recap-clean">✓ No anomalies detected this week</div>', unsafe_allow_html=True)
    st.markdown(rows, unsafe_allow_html=True)


def section_header(title: str, hint: str = "") -> None:
    html = f'<div class="sec-lbl">{title}</div>'
    if hint:
        html += f'<div class="sec-hint">{hint}</div>'
    st.markdown(html, unsafe_allow_html=True)


# --------------------------------------------------------------------------- #
# Sidebar
# --------------------------------------------------------------------------- #
def render_sidebar(weeks_desc: list[str]) -> str:
    with st.sidebar:
        st.markdown(
            '<div style="display:flex;align-items:center;gap:10px;margin-bottom:2px;">'
            '<div style="width:30px;height:30px;border-radius:8px;'
            'background:linear-gradient(135deg,#3B82F6,#2563EB);display:flex;'
            'align-items:center;justify-content:center;color:white;font-weight:800;">R</div>'
            '<span class="side-brand">Revenue Intel</span></div>',
            unsafe_allow_html=True,
        )
        st.markdown('<div class="side-lbl">Reporting Week</div>', unsafe_allow_html=True)
        selected_week = st.selectbox(
            "Reporting week", weeks_desc, index=0, label_visibility="collapsed"
        )

        st.markdown('<div class="side-lbl">Status Legend</div>', unsafe_allow_html=True)
        for label, m in STATUS_META.items():
            st.markdown(
                f'<div class="legend-row"><span class="sw" style="background:{m["color"]};"></span>'
                f'{label}</div>',
                unsafe_allow_html=True,
            )

        st.markdown('<div class="side-lbl">Methodology</div>', unsafe_allow_html=True)
        with st.expander("How variance is scored"):
            # Built from the engine's STATUS_DEFINITIONS so the 5 buckets shown
            # here always match the thresholds actually used to classify.
            defs = "".join(
                f"- **{label}** &mdash; {STATUS_DEFINITIONS[label].replace('+/-', '±')}\n"
                for label in STATUS_ORDER
            )
            st.markdown(
                defs
                + "\nStatus is **direction-aware**: a line beating plan is never "
                "labelled At Risk or Critical.\n\n"
                "Trend is the **slope of variance% over the trailing 4 weeks** "
                "(not just first-vs-last) &mdash; intentionally, so it's resistant to "
                "single-week noise. A line must move roughly 1pp/week to count as "
                "trending rather than stable.\n\n"
                "Anomalies are flagged programmatically and handed to the model as grounding."
            )

        st.markdown('<div class="side-lbl">Data</div>', unsafe_allow_html=True)
        st.markdown(
            '<div style="font-size:0.82rem;color:#64748B;line-height:1.5;">'
            '12 weeks &times; 4 product lines. Narratives are pre-generated by '
            'Claude Opus 4.8 and served from cache &mdash; the live app uses no API key.'
            '</div>',
            unsafe_allow_html=True,
        )
    return selected_week


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> None:
    inject_css()

    df = load_data()
    cache = load_narrative_cache()
    weeks_desc = sorted(df["week_start_date"].unique(), reverse=True)

    selected_week = render_sidebar(weeks_desc)

    summary = calculate_variance(df, week=selected_week)
    narrative = cache.get(selected_week, {})
    wow_pct = _portfolio_wow_pct(df, selected_week)

    # Hero + KPIs
    render_hero(summary)
    render_kpis(summary, wow_pct)
    st.write("")

    # Charts row
    col_a, col_b = st.columns([1, 1], gap="medium")
    with col_a:
        with st.container(border=True):
            section_header("Actual vs. Plan", "By product line, current week")
            st.plotly_chart(build_bar_chart(summary), width="stretch",
                            config={"displayModeBar": False})
    with col_b:
        with st.container(border=True):
            section_header("12-Week Revenue Trend", "Solid = actual, dotted = plan")
            st.plotly_chart(build_trend_chart(df), width="stretch",
                            config={"displayModeBar": False})

    st.write("")

    # Product line performance - full width (the dense 8-column table needs room)
    with st.container(border=True):
        section_header("Product Line Performance")
        render_status_table(summary)

    st.write("")

    # Executive briefing + signals
    col_brief, col_side = st.columns([2, 1], gap="medium")
    with col_brief:
        with st.container(border=True):
            render_narrative(narrative)

            if _has_api_key():
                st.write("")
                if st.button("\U0001F504 Regenerate live (uses your API key)", width="stretch"):
                    with st.spinner("Calling Claude..."):
                        fresh = generate_live_narrative(selected_week)
                    render_narrative(fresh)
    with col_side:
        with st.container(border=True):
            render_signals(summary)

    st.markdown(
        '<div class="foot">Built by <b>Sargam Gupta</b> &middot; Revenue Intelligence Agent '
        '&middot; Powered by the Claude API</div>',
        unsafe_allow_html=True,
    )


main()
