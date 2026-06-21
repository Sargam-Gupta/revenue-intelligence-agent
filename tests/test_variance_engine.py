"""Unit tests for the variance status taxonomy.

These guard the core of the 5-bucket, direction-aware status logic: the exact
boundaries (+/-5, +/-15) and the invariant that a line beating plan can never be
labelled At Risk or Critical (and vice versa).

Runnable two ways:
    py -m pytest tests/test_variance_engine.py      # if pytest is installed
    py tests/test_variance_engine.py                # standalone, no deps
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from analysis.variance_engine import (  # noqa: E402
    AHEAD_OF_PLAN,
    AT_RISK,
    CRITICAL,
    FAVORABLE,
    ON_TRACK,
    classify_status,
)

# (variance_pct, expected_label) covering each band and both sides of every edge.
BOUNDARY_CASES = [
    (-30.0, CRITICAL),
    (-15.1, CRITICAL),
    (-15.0, AT_RISK),     # -15 resolves to the less-severe band
    (-5.1, AT_RISK),
    (-5.0, ON_TRACK),     # -5 is On Track
    (0.0, ON_TRACK),
    (5.0, ON_TRACK),      # +5 is On Track
    (5.1, FAVORABLE),
    (15.0, FAVORABLE),    # +15 is Favorable
    (15.1, AHEAD_OF_PLAN),
    (40.0, AHEAD_OF_PLAN),
]


def test_classify_status_boundaries():
    for variance_pct, expected in BOUNDARY_CASES:
        actual = classify_status(variance_pct)
        assert actual == expected, f"{variance_pct:+}% -> {actual!r}, expected {expected!r}"


def test_status_never_contradicts_sign():
    """A line beating plan is never At Risk/Critical; a miss is never Favorable/Ahead."""
    v = -25.0
    while v <= 25.0:
        label = classify_status(v)
        if v > 0:
            assert label not in (AT_RISK, CRITICAL), f"{v:+}% wrongly labelled {label!r}"
        elif v < 0:
            assert label not in (FAVORABLE, AHEAD_OF_PLAN), f"{v:+}% wrongly labelled {label!r}"
        v = round(v + 0.1, 1)


if __name__ == "__main__":
    test_classify_status_boundaries()
    test_status_never_contradicts_sign()
    print("[OK] all variance status tests passed")
