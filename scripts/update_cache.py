"""Merge one week's narrative into the committed narrative cache.

This is the n8n output-layer step (Node 5, before the git commit/push). It reads
the week key from the variance JSON and the narrative dict from the narrative
JSON, then updates `data/narratives_cache.json` IN PLACE for just that one week,
preserving every other week already in the cache. The single-week diff keeps the
commit small and reviewable.

Run:
    py scripts/update_cache.py --variance run/variance.json --narrative run/narrative.json

Exits non-zero (without touching the cache) if the narrative looks like the
engine's fallback, so a failed Claude call can never overwrite a good cache entry.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE_PATH = ROOT / "data" / "narratives_cache.json"


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge one week's narrative into the cache.")
    parser.add_argument(
        "--variance", required=True,
        help="Path to the variance summary JSON (provides the 'week' key).",
    )
    parser.add_argument(
        "--narrative", required=True,
        help="Path to the narrative JSON to store for that week.",
    )
    parser.add_argument(
        "--cache", default=str(CACHE_PATH),
        help="Cache file to update (default: data/narratives_cache.json).",
    )
    args = parser.parse_args()

    variance = json.loads(Path(args.variance).read_text(encoding="utf-8"))
    narrative = json.loads(Path(args.narrative).read_text(encoding="utf-8"))

    week = variance.get("week")
    if not week:
        sys.exit("ERROR: variance JSON has no 'week' key.")

    # Guard: never persist a fallback / empty narrative. The engine returns a
    # fallback (no top_3_drivers) on API failure; writing that would silently
    # degrade the live dashboard.
    if not narrative.get("executive_summary") or not narrative.get("top_3_drivers"):
        sys.exit(
            f"ERROR: narrative for week {week} looks empty/fallback; "
            "refusing to overwrite the cache."
        )

    cache_path = Path(args.cache)
    cache: dict = {}
    if cache_path.exists():
        cache = json.loads(cache_path.read_text(encoding="utf-8"))

    action = "updated" if week in cache else "added"
    cache[week] = narrative  # in-place if the week exists, appended otherwise

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, indent=2), encoding="utf-8")

    print(f"[OK] {action} narrative for week {week} ({len(cache)} weeks in cache)")


if __name__ == "__main__":
    main()
