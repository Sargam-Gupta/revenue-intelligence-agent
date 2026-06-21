"""Variance calculation engine.

Turns the raw revenue dataframe into a clean, structured summary for any given
week: per-product-line variance, portfolio totals, week-over-week change, a
4-week trend direction, and a list of programmatically-detected anomalies.

The output dict is the single source of truth consumed by both the AI narrative
engine and the Streamlit dashboard.
"""

from __future__ import annotations

import pandas as pd

# --------------------------------------------------------------------------- #
# Status taxonomy - the SINGLE SOURCE OF TRUTH for the 5 status buckets.
#
# Status is direction-aware: beating plan and missing plan never share a label.
# Everything downstream (the dashboard's colors/legend/signal counts and the AI
# narrative prompt's taxonomy text) is derived from STATUS_ORDER / STATUS_DEFINITIONS
# below, so the buckets are defined in exactly one place.
# --------------------------------------------------------------------------- #
ON_TRACK_LIMIT = 5.0    # within +/-5% of plan is "On Track"
AT_RISK_LIMIT = 15.0    # the +/-15% boundary between the moderate and extreme bands

# Status labels (module constants so the classifier and the metadata below can
# never drift out of sync via a typo).
AHEAD_OF_PLAN = "Ahead of Plan"
FAVORABLE = "Favorable"
ON_TRACK = "On Track"
AT_RISK = "At Risk"
CRITICAL = "Critical"

# Presentation order: best performance first, worst last. Consumed by the
# dashboard legend and the "This Week's Signals" recap so they list all 5 buckets.
STATUS_ORDER = [AHEAD_OF_PLAN, FAVORABLE, ON_TRACK, AT_RISK, CRITICAL]

# Plain-language definition of each bucket. The narrative engine renders these
# verbatim into the prompt so the model always describes the labels correctly.
# ASCII only ("+/-") so these strings are safe to print on a cp1252 console.
STATUS_DEFINITIONS = {
    AHEAD_OF_PLAN: "more than 15% above plan - notable overperformance, may indicate a forecasting gap",
    FAVORABLE: "5% to 15% above plan",
    ON_TRACK: "within +/-5% of plan",
    AT_RISK: "5% to 15% below plan",
    CRITICAL: "more than 15% below plan",
}

TREND_WEEKS = 4         # rolling window for trend direction
# Slope thresholds of +/-1.0 percentage points per week were chosen to filter out
# single-week noise while still catching multi-week directional shifts. A line
# needs to be moving roughly 1pp/week in variance% to be classified as trending,
# rather than stable.
TREND_FLAT_BAND = 1.0   # |slope of variance%| below this is "Stable"

PRODUCT_LINE_ORDER = ["Enterprise", "SMB", "API", "Consulting"]


def classify_status(variance_pct: float) -> str:
    """Map a signed variance percentage to one of the 5 direction-aware buckets.

    Boundaries resolve to the *less severe* band (toward On Track):
        v < -15            -> Critical
        -15 <= v < -5      -> At Risk
        -5 <= v <= +5      -> On Track
        +5 < v <= +15      -> Favorable
        v > +15            -> Ahead of Plan
    """
    if variance_pct < -AT_RISK_LIMIT:
        return CRITICAL
    if variance_pct < -ON_TRACK_LIMIT:
        return AT_RISK
    if variance_pct <= ON_TRACK_LIMIT:
        return ON_TRACK
    if variance_pct <= AT_RISK_LIMIT:
        return FAVORABLE
    return AHEAD_OF_PLAN


def _sorted_weeks(df: pd.DataFrame) -> list[str]:
    """Unique week_start_date values as ISO strings, oldest first."""
    return sorted(df["week_start_date"].astype(str).unique())


def _trend_direction(line_history: pd.DataFrame) -> str:
    """Determine trend from the last TREND_WEEKS of actual-vs-plan variance.

    Uses the slope of variance% over the recent window: a rising variance
    (actuals improving relative to plan) is "Improving", a falling one is
    "Declining", and a near-flat slope is "Stable".
    """
    recent = line_history.tail(TREND_WEEKS)
    if len(recent) < 2:
        return "Stable"

    variance_pct = (recent["actual_revenue"] - recent["plan_revenue"]) / recent["plan_revenue"] * 100
    # Slope per week via a simple linear fit over 0..n-1.
    x = range(len(variance_pct))
    n = len(variance_pct)
    mean_x = sum(x) / n
    mean_y = variance_pct.mean()
    numerator = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, variance_pct))
    denominator = sum((xi - mean_x) ** 2 for xi in x)
    slope = numerator / denominator if denominator else 0.0

    if slope > TREND_FLAT_BAND:
        return "Improving"
    if slope < -TREND_FLAT_BAND:
        return "Declining"
    return "Stable"


def _consecutive_decline_weeks(line_history: pd.DataFrame) -> int:
    """Count trailing weeks where actual revenue fell vs the prior week."""
    actuals = line_history["actual_revenue"].tolist()
    streak = 0
    for i in range(len(actuals) - 1, 0, -1):
        if actuals[i] < actuals[i - 1]:
            streak += 1
        else:
            break
    return streak


def _consecutive_ahead_weeks(line_history: pd.DataFrame) -> int:
    """Count trailing weeks where actual beat plan by more than +15% (Ahead of Plan).

    Tied to AT_RISK_LIMIT so this streak always means "Ahead of Plan status
    persisting" - it can't drift away from the status band definition.
    """
    actual = line_history["actual_revenue"].tolist()
    plan = line_history["plan_revenue"].tolist()
    streak = 0
    for i in range(len(actual) - 1, -1, -1):
        if plan[i] and (actual[i] - plan[i]) / plan[i] * 100 > AT_RISK_LIMIT:
            streak += 1
        else:
            break
    return streak


def calculate_variance(df: pd.DataFrame, week: str | None = None) -> dict:
    """Compute the structured variance summary for one week.

    Args:
        df: The full revenue dataframe (all weeks, all product lines).
        week: ISO date string of the week to analyze. Defaults to most recent.

    Returns:
        A dict with keys: week, portfolio, product_lines, anomalies.
    """
    df = df.copy()
    df["week_start_date"] = df["week_start_date"].astype(str)

    weeks = _sorted_weeks(df)
    if not weeks:
        raise ValueError("No data: the revenue dataframe is empty.")

    target_week = week or weeks[-1]
    if target_week not in weeks:
        raise ValueError(f"Week {target_week!r} not found in data. Available: {weeks}")

    week_index = weeks.index(target_week)
    prev_week = weeks[week_index - 1] if week_index > 0 else None

    current = df[df["week_start_date"] == target_week]

    product_lines: dict[str, dict] = {}
    anomalies: list[str] = []

    # Stable ordering for presentation; fall back to whatever's in the data.
    lines = [pl for pl in PRODUCT_LINE_ORDER if pl in set(current["product_line"])]
    lines += [pl for pl in current["product_line"].unique() if pl not in lines]

    for line in lines:
        row = current[current["product_line"] == line].iloc[0]
        actual = float(row["actual_revenue"])
        plan = float(row["plan_revenue"])
        variance_dollars = actual - plan
        variance_pct = round(variance_dollars / plan * 100, 1) if plan else 0.0

        # Week-over-week change vs the previous week's actual for this line.
        wow_change_pct = 0.0
        if prev_week is not None:
            prev_row = df[(df["week_start_date"] == prev_week) & (df["product_line"] == line)]
            if not prev_row.empty:
                prev_actual = float(prev_row.iloc[0]["actual_revenue"])
                if prev_actual:
                    wow_change_pct = round((actual - prev_actual) / prev_actual * 100, 1)

        status = classify_status(variance_pct)

        # Trend uses history up to and including the target week.
        line_history = (
            df[(df["product_line"] == line) & (df["week_start_date"] <= target_week)]
            .sort_values("week_start_date")
        )
        trend = _trend_direction(line_history)

        product_lines[line] = {
            "actual": round(actual, 2),
            "plan": round(plan, 2),
            "variance_dollars": round(variance_dollars, 2),
            "variance_pct": variance_pct,
            "wow_change_pct": wow_change_pct,
            "status": status,
            "trend": trend,
        }

        # --- Anomaly detection (data-grounded, for the AI to reference) ---
        # Critical is now always a miss (the 5-bucket taxonomy routes large
        # upside to Ahead of Plan), so this only flags downside.
        if status == CRITICAL:
            anomalies.append(
                f"{line} variance is {variance_pct:+.1f}% - beyond the -15% threshold, flagged as Critical"
            )

        decline_streak = _consecutive_decline_weeks(line_history)
        if decline_streak >= 3:
            anomalies.append(f"{line} has declined for {decline_streak} consecutive weeks")

        # Sustained upside is also a reportable signal (under-forecasting,
        # pulled-forward revenue, or a one-time event worth understanding).
        ahead_streak = _consecutive_ahead_weeks(line_history)
        if ahead_streak >= 2:
            anomalies.append(
                f"{line} has beaten plan by more than 15% for {ahead_streak} consecutive weeks - review forecast assumptions"
            )

    # --- Portfolio rollup ---
    total_actual = float(current["actual_revenue"].sum())
    total_plan = float(current["plan_revenue"].sum())
    portfolio_variance_dollars = total_actual - total_plan
    portfolio_variance_pct = round(portfolio_variance_dollars / total_plan * 100, 1) if total_plan else 0.0

    portfolio = {
        "total_actual": round(total_actual, 2),
        "total_plan": round(total_plan, 2),
        "variance_dollars": round(portfolio_variance_dollars, 2),
        "variance_pct": portfolio_variance_pct,
        "status": classify_status(portfolio_variance_pct),
    }

    return {
        "week": target_week,
        "portfolio": portfolio,
        "product_lines": product_lines,
        "anomalies": anomalies,
    }


if __name__ == "__main__":
    import json
    from pathlib import Path

    csv_path = Path(__file__).resolve().parent.parent / "data" / "revenue_data.csv"
    frame = pd.read_csv(csv_path)
    summary = calculate_variance(frame)
    print(json.dumps(summary, indent=2))
