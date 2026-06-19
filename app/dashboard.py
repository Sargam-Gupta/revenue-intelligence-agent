"""Revenue Intelligence Agent - Streamlit dashboard.

Interactive front end. Reads the generated revenue CSV and the pre-generated
narrative cache; renders metrics, charts, a status table, and the AI commentary.

The deployed (public) app needs no API key: narratives come from the committed
cache. When an ANTHROPIC_API_KEY is available locally, an optional
"Regenerate live" control appears for on-the-fly generation.

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

from analysis.variance_engine import calculate_variance  # noqa: E402

CSV_PATH = ROOT / "data" / "revenue_data.csv"
CACHE_PATH = ROOT / "data" / "narratives_cache.json"

# Brand-ish palette: deep slate + a single warm accent. Deliberately NOT the
# default cream/serif look, and not generic purple-on-white.
COLOR_ACTUAL = "#2563EB"   # blue
COLOR_PLAN = "#9CA3AF"     # gray
STATUS_COLORS = {
    "On Track": "#16A34A",  # green
    "At Risk": "#D97706",   # amber
    "Critical": "#DC2626",  # red
}

st.set_page_config(page_title="Revenue Intelligence Agent", layout="wide")


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


# --------------------------------------------------------------------------- #
# Charts
# --------------------------------------------------------------------------- #
def build_bar_chart(summary: dict) -> go.Figure:
    lines = list(summary["product_lines"].keys())
    actual = [summary["product_lines"][l]["actual"] for l in lines]
    plan = [summary["product_lines"][l]["plan"] for l in lines]

    fig = go.Figure()
    fig.add_bar(name="Actual", x=lines, y=actual, marker_color=COLOR_ACTUAL)
    fig.add_bar(name="Plan", x=lines, y=plan, marker_color=COLOR_PLAN)
    fig.update_layout(
        title=f"Actual vs. Plan by Product Line - Week of {summary['week']}",
        barmode="group",
        template="plotly_white",
        yaxis_title="Revenue (USD)",
        yaxis_tickprefix="$",
        yaxis_tickformat=",.0f",
        legend_title_text="",
        margin=dict(t=60, b=40, l=20, r=20),
        height=420,
    )
    return fig


def build_trend_chart(df: pd.DataFrame) -> go.Figure:
    weeks = sorted(df["week_start_date"].unique())
    lines = [l for l in ["Enterprise", "SMB", "API", "Consulting"] if l in set(df["product_line"])]

    palette = ["#2563EB", "#16A34A", "#D97706", "#9333EA"]
    fig = go.Figure()
    for i, line in enumerate(lines):
        sub = df[df["product_line"] == line].sort_values("week_start_date")
        color = palette[i % len(palette)]
        fig.add_scatter(
            x=sub["week_start_date"], y=sub["actual_revenue"],
            mode="lines+markers", name=f"{line} (Actual)",
            line=dict(color=color, width=2.5),
        )
        fig.add_scatter(
            x=sub["week_start_date"], y=sub["plan_revenue"],
            mode="lines", name=f"{line} (Plan)",
            line=dict(color=color, width=1.2, dash="dash"),
            opacity=0.6, showlegend=False,
        )

    fig.update_layout(
        title="12-Week Revenue Trend by Product Line (solid = actual, dashed = plan)",
        template="plotly_white",
        yaxis_title="Revenue (USD)",
        yaxis_tickprefix="$",
        yaxis_tickformat=",.0f",
        xaxis_title="Week",
        legend_title_text="",
        margin=dict(t=60, b=40, l=20, r=20),
        height=460,
    )
    return fig


# --------------------------------------------------------------------------- #
# Status table
# --------------------------------------------------------------------------- #
def build_status_table(summary: dict) -> pd.DataFrame:
    rows = []
    for name, pl in summary["product_lines"].items():
        rows.append(
            {
                "Product Line": name,
                "Actual": pl["actual"],
                "Plan": pl["plan"],
                "Variance $": pl["variance_dollars"],
                "Variance %": pl["variance_pct"],
                "WoW Change": pl["wow_change_pct"],
                "Status": pl["status"],
                "Trend": pl["trend"],
            }
        )
    return pd.DataFrame(rows)


def style_status_table(table: pd.DataFrame):
    def color_status(val: str) -> str:
        color = STATUS_COLORS.get(val, "#374151")
        return f"background-color: {color}; color: white; font-weight: 600;"

    styler = (
        table.style.map(color_status, subset=["Status"])
        .format(
            {
                "Actual": "${:,.0f}",
                "Plan": "${:,.0f}",
                "Variance $": "${:,.0f}",
                "Variance %": "{:+.1f}%",
                "WoW Change": "{:+.1f}%",
            }
        )
    )
    return styler


# --------------------------------------------------------------------------- #
# Layout
# --------------------------------------------------------------------------- #
def render_metrics(summary: dict) -> None:
    p = summary["portfolio"]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Actual Revenue", f"${p['total_actual']:,.0f}")
    c2.metric("Total Plan Revenue", f"${p['total_plan']:,.0f}")
    # delta drives Streamlit's built-in red/green coloring (down = red).
    c3.metric("Variance $", f"${p['variance_dollars']:,.0f}", delta=f"{p['variance_dollars']:,.0f}")
    c4.metric("Variance %", f"{p['variance_pct']:+.1f}%", delta=f"{p['variance_pct']:+.1f}%")


def render_narrative(narrative: dict) -> None:
    st.subheader("AI-Generated Executive Commentary")
    st.info("Generated by Claude AI based on this week's variance data")

    if not narrative or not narrative.get("executive_summary"):
        st.warning("No narrative available for this week.")
        return

    st.markdown("**Executive Summary**")
    st.write(narrative["executive_summary"])

    st.markdown("**Top 3 Drivers**")
    for driver in narrative.get("top_3_drivers", []):
        st.markdown(f"- {driver}")

    st.markdown("**Risk Flag**")
    st.write(narrative.get("risk_flag", ""))


def main() -> None:
    # Header
    st.title("Revenue Intelligence Agent")
    st.caption("Automated weekly revenue variance analysis powered by AI")
    st.divider()

    df = load_data()
    cache = load_narrative_cache()
    weeks_desc = sorted(df["week_start_date"].unique(), reverse=True)

    # Controls
    ctrl_l, ctrl_r = st.columns([3, 1])
    selected_week = ctrl_l.selectbox("Select a week to analyze", weeks_desc, index=0)
    run = ctrl_r.button("Run Analysis", type="primary", width="stretch")

    if not run:
        st.info("Pick a week and click **Run Analysis** to generate the report.")
        _render_footer()
        return

    with st.spinner("Running analysis and generating narrative..."):
        summary = calculate_variance(df, week=selected_week)
        narrative = cache.get(selected_week, {})

    # 1. Portfolio metrics
    render_metrics(summary)
    st.divider()

    # 2 & 3. Charts
    st.plotly_chart(build_bar_chart(summary), width="stretch")
    st.plotly_chart(build_trend_chart(df), width="stretch")

    # 4. Status table
    st.markdown("#### Product Line Status")
    st.dataframe(
        style_status_table(build_status_table(summary)),
        width="stretch",
        hide_index=True,
    )
    st.divider()

    # 5. AI narrative
    render_narrative(narrative)

    # Optional gated live regeneration (local dev only)
    if _has_api_key():
        if st.button("🔄 Regenerate live (uses your API key)"):
            with st.spinner("Calling Claude..."):
                fresh = generate_live_narrative(selected_week)
            render_narrative(fresh)

    _render_footer()


def _render_footer() -> None:
    st.divider()
    st.caption("Built by Sargam Gupta · Revenue Intelligence Agent · Powered by Claude API")


main()
