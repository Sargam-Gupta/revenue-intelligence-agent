# Changes 1 — Variance Status Logic Fix

## Context

The current variance engine (`analysis/variance_engine.py`) uses a 3-bucket status system based on `|variance_pct|` (absolute value vs. plan):

```
On Track:  |variance_pct| <= 5%
At Risk:   5% < |variance_pct| <= 15%
Critical:  |variance_pct| > 15%
```

**The problem:** This treats favorable and unfavorable variance identically. A product line beating plan by +5.3% gets labeled "At Risk" — the same label used for a line *missing* plan by 5.3%. In real FP&A reporting, "At Risk" specifically means at risk of missing a target. Beating plan by a wide margin is a different situation (often called "Favorable" or "Ahead of Plan") and should never share a label with underperformance.

This was visible in the dashboard: API was +5.3% vs. plan with +13.1% WoW growth, but displayed as "At Risk" — which reads as a contradiction to anyone reviewing the numbers, and undermines the narrative quality.

---

## Change 1: Replace the 3-bucket status system with a 5-bucket, direction-aware system

**File:** `analysis/variance_engine.py`

Replace the current status logic with the following. Status must now depend on the **sign** of `variance_pct`, not just its absolute value.

```
variance_pct > +15%              → "Ahead of Plan"
+5%  < variance_pct <= +15%      → "Favorable"
-5%  <= variance_pct <= +5%      → "On Track"
-15% <= variance_pct < -5%       → "At Risk"
variance_pct < -15%              → "Critical"
```

### Requirements:
- Apply this to both the per-product-line status and the portfolio-level status.
- Update any color-coding logic tied to status:
  - "On Track" → green
  - "Favorable" → light green / teal (distinct from "On Track" green)
  - "Ahead of Plan" → blue or a distinct accent color (this is notable, not necessarily "good news with no caveats" — overperformance can signal forecasting error)
  - "At Risk" → orange/yellow (unchanged)
  - "Critical" → red (unchanged)
- Update the **Status Legend** in the sidebar to reflect all 5 statuses, not 3.
- Update the **"This Week's Signals"** panel to count all 5 buckets, not just 3.

### Verification:
After this change, re-run the dashboard for the weeks already used in testing (e.g., 2026-05-25 and 2026-05-04) and confirm:
- API at +5.3% vs. plan now reads "Favorable," not "At Risk"
- No row shows a status that contradicts its variance sign

---

## Change 2: Update the AI narrative prompt to reflect the new status taxonomy

**File:** `ai/narrative_engine.py`

The prompt sent to Claude must be updated so the model understands the 5-bucket system and doesn't generate confusing language (e.g., "despite its At Risk status" when a line is actually beating plan).

### Requirements:
- In the system or user prompt, briefly explain the status taxonomy so Claude uses the labels correctly in the narrative:
  ```
  Status definitions:
  - "Ahead of Plan": more than 15% above plan — notable overperformance, may indicate a forecasting gap
  - "Favorable": 5–15% above plan
  - "On Track": within ±5% of plan
  - "At Risk": 5–15% below plan
  - "Critical": more than 15% below plan
  ```
- Instruct Claude explicitly: "Never use 'At Risk' or 'Critical' to describe a product line that is beating plan. Use 'Favorable' or 'Ahead of Plan' instead."
- Re-test the narrative generation for a week where a product line is in "Favorable" or "Ahead of Plan" territory, and confirm the language is now consistent (e.g., "API beat plan by 5.3%, a favorable result" rather than anything implying risk).

---

## Change 3: Add favorable-variance anomaly detection

**File:** `analysis/variance_engine.py`

Currently, anomaly detection only flags bad news: lines with "Critical" status, or lines that declined for 3+ consecutive weeks. Add detection for large favorable anomalies too, since unexpected upside is also a reportable signal in real FP&A (it can indicate under-forecasting, a pull-forward of revenue, or a one-time event worth understanding).

### Requirements:
Add the following anomaly rule:
- Flag any product line where `variance_pct > +15%` (i.e., "Ahead of Plan") for **2 or more consecutive weeks**.
- Anomaly message format: `"{product_line} has beaten plan by double digits for {n} consecutive weeks — review forecast assumptions."`

This anomaly should appear in the same `anomalies` list already used for Critical/declining flags, and should be passed to the AI narrative engine the same way so it can be referenced in the Risk Flag or Key Drivers section when relevant.

### Verification:
Test against a sample week where a product line has been significantly ahead of plan for 2+ weeks in a row, and confirm the anomaly appears in both the "This Week's Signals" panel and the AI narrative.

---

## Change 4: Document the trend slope thresholds

**File:** `analysis/variance_engine.py` (code comments) and `README.md` (methodology section)

The trend logic (regression slope on variance% over trailing 4 weeks, with Improving > +1.0 and Declining < -1.0) is sound but currently undocumented — the thresholds look arbitrary without explanation.

### Requirements:
- Add a code comment above the trend calculation explaining: "Slope thresholds of +/-1.0 percentage points per week were chosen to filter out single-week noise while still catching multi-week directional shifts. A line needs to be moving roughly 1pp/week in variance% to be classified as trending, rather than stable."
- Add a short note in the README's methodology section (or the "How variance is scored" expandable in the dashboard sidebar) that trend is based on a 4-week trailing regression slope, not just a first-vs-last comparison — and that this is intentional because it's more resistant to single-week noise.

---

## Build Order

1. Implement Change 1 (status logic) first — this is the core fix.
2. Re-run the dashboard and visually confirm the fix using the two weeks already screenshotted (2026-05-25, 2026-05-04).
3. Implement Change 2 (prompt update) and regenerate narratives for the same test weeks — confirm language now matches the new statuses.
4. Implement Change 3 (favorable anomaly detection).
5. Implement Change 4 (documentation) last — no functional change, just clarity for anyone reviewing the code or methodology.

## What Success Looks Like

- No product line ever shows "At Risk" or "Critical" while beating plan, and no product line ever shows "Favorable" or "Ahead of Plan" while missing plan.
- The AI narrative never describes a favorable variance using risk language.
- The methodology section clearly explains all 5 statuses and the trend slope logic, so an interviewer reading the README or clicking "How variance is scored" has no unanswered questions about the logic.
