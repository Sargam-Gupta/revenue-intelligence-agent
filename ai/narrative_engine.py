"""AI narrative engine.

Takes the structured variance summary and asks Claude (Opus 4.8) to write an
executive-ready revenue commentary. Uses the Anthropic SDK's structured-output
path (`messages.parse` + a Pydantic schema) so the three sections come back as
clean, separately-renderable fields instead of one blob of text.

This module is the only code that spends API tokens. In the deployed app it is
NOT called — the dashboard reads pre-generated narratives from the cache. It is
invoked locally by `scripts/pregenerate.py` (and optionally by a gated
"regenerate live" button when an API key is present).
"""

from __future__ import annotations

from typing import Any

from dotenv import load_dotenv
from pydantic import BaseModel, Field

# The status taxonomy is owned by the variance engine; import it so the prompt's
# definitions can never drift from the thresholds the dashboard actually uses.
try:
    from analysis.variance_engine import STATUS_DEFINITIONS, STATUS_ORDER
except ModuleNotFoundError:  # running this file standalone, before sys.path is set
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from analysis.variance_engine import STATUS_DEFINITIONS, STATUS_ORDER

# Load ANTHROPIC_API_KEY from a local .env if present. On Streamlit Cloud the
# key is injected via the secret store; in the cached-only deploy it's absent
# and that's fine because generate_narrative is never called there.
load_dotenv()

MODEL = "claude-opus-4-8"
MAX_TOKENS = 2000


def _status_taxonomy_block() -> str:
    """Render the engine's status buckets as prompt text, in presentation order."""
    lines = ["Status definitions (based on actual-vs-plan variance):"]
    lines += [f'- "{label}": {STATUS_DEFINITIONS[label]}' for label in STATUS_ORDER]
    lines.append(
        'Never describe a product line that is beating plan as "At Risk" or '
        '"Critical" - use "Favorable" or "Ahead of Plan". Likewise, never describe '
        'a line that is missing plan as "Favorable" or "Ahead of Plan".'
    )
    return "\n".join(lines)


# The taxonomy is stable context (it doesn't change per week), so it lives in the
# system prompt rather than the per-week user message.
SYSTEM_PROMPT = (
    "You are a senior FP&A analyst at a technology company. You write concise, "
    "accurate, and actionable revenue variance commentaries for executive audiences. "
    "Your output is always structured, data-specific, and free of filler language.\n\n"
    + _status_taxonomy_block()
)

FALLBACK_NARRATIVE: dict[str, Any] = {
    "executive_summary": "Narrative generation failed. Please check API key and connection.",
    "top_3_drivers": [],
    "risk_flag": "",
}


class ExecutiveNarrative(BaseModel):
    """Schema Claude must fill — guarantees three clean, typed sections."""

    executive_summary: str = Field(
        description=(
            "3 sentences max: overall portfolio performance this week, the single "
            "biggest driver of variance, and the business implication. Use specific "
            "numbers from the data."
        )
    )
    top_3_drivers: list[str] = Field(
        description=(
            "Exactly three bullet points naming the most significant factors "
            "explaining this week's performance. Be specific - use product line "
            "names and percentages."
        )
    )
    risk_flag: str = Field(
        description=(
            "One sentence: the single most important trend or risk finance "
            "leadership should watch next week."
        )
    )


def _build_user_message(summary: dict) -> str:
    """Render the variance dict into the prompt block the analyst persona reads."""
    p = summary["portfolio"]

    lines = [
        "Here is this week's revenue performance data:",
        "",
        "PORTFOLIO SUMMARY",
        f"Week of: {summary['week']}",
        f"Total Actual Revenue: ${p['total_actual']:,.0f}",
        f"Total Plan Revenue: ${p['total_plan']:,.0f}",
        f"Total Variance: ${p['variance_dollars']:,.0f} ({p['variance_pct']:+.1f}%)",
        f"Portfolio Status: {p['status']}",
        "",
        "PRODUCT LINE BREAKDOWN",
    ]

    for name, pl in summary["product_lines"].items():
        lines.append(
            f"- {name}: actual ${pl['actual']:,.0f}, plan ${pl['plan']:,.0f}, "
            f"variance {pl['variance_pct']:+.1f}%, WoW {pl['wow_change_pct']:+.1f}%, "
            f"status {pl['status']}, trend {pl['trend']}"
        )

    lines += ["", "ANOMALIES DETECTED"]
    if summary["anomalies"]:
        lines += [f"- {a}" for a in summary["anomalies"]]
    else:
        lines.append("- None flagged this week.")

    lines += [
        "",
        "Based on this data, write the executive summary, top 3 drivers, and risk "
        "flag. Use specific numbers from the data above. Be concise and avoid filler.",
    ]
    return "\n".join(lines)


def generate_narrative(variance_summary: dict) -> dict:
    """Generate the executive narrative for one week's variance summary.

    Returns a dict: {executive_summary, top_3_drivers, risk_flag}.
    On any API failure, returns FALLBACK_NARRATIVE rather than raising, so callers
    (pregeneration loop, dashboard) degrade gracefully.
    """
    # Imported here so the module is importable without the SDK installed
    # (e.g. on a cache-only deploy that never calls this function).
    import anthropic

    client = anthropic.Anthropic()
    user_message = _build_user_message(variance_summary)

    try:
        response = client.messages.parse(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
            output_format=ExecutiveNarrative,
        )
    except anthropic.APIError as exc:
        print(f"[narrative_engine] API error: {exc}")
        return dict(FALLBACK_NARRATIVE)
    except Exception as exc:  # network / unexpected
        print(f"[narrative_engine] Unexpected error: {exc}")
        return dict(FALLBACK_NARRATIVE)

    narrative = response.parsed_output
    if narrative is None:
        print("[narrative_engine] Model did not return a parseable narrative.")
        return dict(FALLBACK_NARRATIVE)

    print("[OK] Narrative generated successfully")
    return narrative.model_dump()


if __name__ == "__main__":
    import json
    from pathlib import Path

    import pandas as pd

    # Allow running this file directly for a quick standalone smoke test.
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from analysis.variance_engine import calculate_variance

    csv_path = Path(__file__).resolve().parent.parent / "data" / "revenue_data.csv"
    df = pd.read_csv(csv_path)
    summary = calculate_variance(df)
    result = generate_narrative(summary)
    print(json.dumps(result, indent=2))
