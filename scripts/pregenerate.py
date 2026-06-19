"""Pre-generate executive narratives for every week and cache them to disk.

Run this ONCE locally (with an ANTHROPIC_API_KEY in your .env), then commit the
resulting data/narratives_cache.json. The deployed Streamlit app reads that
cache and therefore needs no API key and spends no tokens.

Run:
    python scripts/pregenerate.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ai.narrative_engine import generate_narrative  # noqa: E402
from analysis.variance_engine import calculate_variance  # noqa: E402

CSV_PATH = ROOT / "data" / "revenue_data.csv"
CACHE_PATH = ROOT / "data" / "narratives_cache.json"


def main() -> None:
    if not CSV_PATH.exists():
        sys.exit(f"Missing {CSV_PATH}. Run `python data/generate_data.py` first.")

    df = pd.read_csv(CSV_PATH)
    weeks = sorted(df["week_start_date"].astype(str).unique())

    cache: dict[str, dict] = {}
    for i, week in enumerate(weeks, start=1):
        print(f"[{i}/{len(weeks)}] Generating narrative for week of {week} ...")
        summary = calculate_variance(df, week=week)
        narrative = generate_narrative(summary)
        cache[week] = narrative

    CACHE_PATH.write_text(json.dumps(cache, indent=2), encoding="utf-8")
    print(f"\nWrote {len(cache)} narratives to {CACHE_PATH}")

    # Surface any weeks that fell back to the error narrative.
    failed = [w for w, n in cache.items() if not n.get("top_3_drivers")]
    if failed:
        print(f"WARNING: {len(failed)} week(s) returned the fallback narrative: {failed}")
        print("Check your ANTHROPIC_API_KEY / connection and re-run.")


if __name__ == "__main__":
    main()
