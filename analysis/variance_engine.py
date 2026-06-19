"""Variance calculation engine.

Turns the raw revenue dataframe into a clean, structured summary for any given
week: per-product-line variance, portfolio totals, week-over-week change, a
4-week trend direction, and a list of programmatically-detected anomalies.

The output dict is the single source of truth consumed by both the AI narrative
engine and the Streamlit dashboard.
"""

from __future__ import annotations

import pandas as pd

# Status thresholds, expressed as absolute variance percentage from plan.
ON_TRACK_LIMIT = 5.0    # within +/-5%
AT_RISK_LIMIT = 15.0    # +/-5% to +/-15%; beyond +/-15% is Critical

TREND_WEEKS = 4         # rolling window for trend direction
TREND_FLAT_BAND = 1.0   # |slope of variance%| below this is "Stable"

PRODUCT_LINE_ORDER = ["Enterprise", "SMB", "API", "Consulting"]


def _status_from_variance_pct(variance_pct: float) -> str:
    """Map a signed variance percentage to a status label."""
    magnitude = abs(variance_pct)
    if magnitude <= ON_TRACK_LIMIT:
        return "On Track"
    if magnitude <= AT_RISK_LIMIT:
        return "At Risk"
    return "Critical"


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

        status = _status_from_variance_pct(variance_pct)

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
        if status == "Critical":
            if variance_pct < 0:
                anomalies.append(
                    f"{line} variance is {variance_pct:+.1f}% - beyond the -15% threshold, flagged as Critical"
                )
            else:
                anomalies.append(
                    f"{line} beats plan by {variance_pct:+.1f}% - an unusually large upside vs plan"
                )

        decline_streak = _consecutive_decline_weeks(line_history)
        if decline_streak >= 3:
            anomalies.append(f"{line} has declined for {decline_streak} consecutive weeks")

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
        "status": _status_from_variance_pct(portfolio_variance_pct),
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
