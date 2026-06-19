"""Generate a realistic simulated weekly revenue dataset.

Produces 12 weeks x 4 product lines = 48 rows of actual-vs-plan revenue with
deliberate, hand-planted anomalies so the variance engine and the AI narrative
have a meaningful story to tell.

Run:
    python data/generate_data.py

Output:
    data/revenue_data.csv
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

# Reproducible: the same seed -> the same dataset -> the same planted story,
# on every machine and every run. This matters because the narrative cache is
# generated against this exact data.
RNG = np.random.default_rng(42)

PRODUCT_LINES = ["Enterprise", "SMB", "API", "Consulting"]

# Weekly plan baseline (midpoint) per product line, in USD.
PLAN_BASELINE = {
    "Enterprise": 200_000,   # ~$180k-$220k
    "SMB": 100_000,          # ~$90k-$110k
    "API": 50_000,           # ~$45k-$55k
    "Consulting": 30_000,    # ~$25k-$35k
}

# Small week-to-week wobble applied to the plan baseline so plan isn't a flat line.
PLAN_WOBBLE_PCT = 0.04

# Normal actual-vs-plan variance: most weeks land within +/-8% of plan.
NORMAL_VARIANCE_PCT = 0.08

NUM_WEEKS = 12  # weeks are numbered 1..12, with week 12 = most recent

# Deliberate anomalies, keyed by (week_number, product_line) -> actual/plan ratio.
# Week numbers are 1-indexed from oldest (1) to newest (12).
PLANTED_ANOMALIES = {
    (4, "Enterprise"): 0.78,   # lost deal: misses plan by 22%
    (7, "SMB"): 1.18,          # campaign spike: beats plan by 18%
    (10, "API"): 0.85,         # churn event: misses plan by 15%
}

# Week 12: nudge the whole portfolio slightly below plan to set up the narrative.
WEEK12_PORTFOLIO_RATIO = 0.97


def _most_recent_monday(today: date | None = None) -> date:
    """Return the Monday of the current week (or the given day's week)."""
    today = today or date.today()
    return today - timedelta(days=today.weekday())


def _week_start_dates() -> list[date]:
    """12 consecutive Mondays, oldest first, ending at the current week."""
    latest_monday = _most_recent_monday()
    # week index 1 = 11 weeks ago, week index 12 = current week
    return [latest_monday - timedelta(weeks=(NUM_WEEKS - 1 - i)) for i in range(NUM_WEEKS)]


def generate_dataframe() -> pd.DataFrame:
    """Build the 48-row revenue dataframe."""
    weeks = _week_start_dates()
    rows: list[dict] = []

    for week_idx, week_start in enumerate(weeks, start=1):
        is_last_week = week_idx == NUM_WEEKS

        for line in PRODUCT_LINES:
            # Plan revenue: baseline with a small deterministic-ish wobble.
            plan_factor = 1.0 + RNG.uniform(-PLAN_WOBBLE_PCT, PLAN_WOBBLE_PCT)
            plan_revenue = PLAN_BASELINE[line] * plan_factor

            # Decide the actual-vs-plan ratio.
            if (week_idx, line) in PLANTED_ANOMALIES:
                ratio = PLANTED_ANOMALIES[(week_idx, line)]
            elif is_last_week:
                # Most recent week: keep the portfolio modestly below plan.
                # Tight band centered just under the WEEK12 target ratio.
                ratio = WEEK12_PORTFOLIO_RATIO + RNG.uniform(-0.015, 0.015)
            else:
                ratio = 1.0 + RNG.uniform(-NORMAL_VARIANCE_PCT, NORMAL_VARIANCE_PCT)

            actual_revenue = plan_revenue * ratio

            rows.append(
                {
                    "week_start_date": week_start.isoformat(),
                    "product_line": line,
                    "actual_revenue": round(actual_revenue, 2),
                    "plan_revenue": round(plan_revenue, 2),
                }
            )

    df = pd.DataFrame(rows, columns=["week_start_date", "product_line", "actual_revenue", "plan_revenue"])
    return df


def main() -> None:
    df = generate_dataframe()

    out_path = Path(__file__).resolve().parent / "revenue_data.csv"
    df.to_csv(out_path, index=False)

    print(f"Wrote {len(df)} rows to {out_path}")
    print("\nPreview (first 10 rows):")
    print(df.head(10).to_string(index=False))

    # Quick sanity check on the most recent week's portfolio variance.
    latest_week = df["week_start_date"].max()
    latest = df[df["week_start_date"] == latest_week]
    total_actual = latest["actual_revenue"].sum()
    total_plan = latest["plan_revenue"].sum()
    variance_pct = (total_actual - total_plan) / total_plan * 100
    print(
        f"\nMost recent week ({latest_week}) portfolio variance: "
        f"{variance_pct:+.1f}%  (actual ${total_actual:,.0f} vs plan ${total_plan:,.0f})"
    )


if __name__ == "__main__":
    main()
