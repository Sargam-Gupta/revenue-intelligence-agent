# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this is

**Revenue Intelligence Agent** — a Finance × AI portfolio project. It reads weekly
actual-vs-plan revenue across 4 product lines, computes variance/anomaly metrics,
uses the Claude API to write executive commentary, and serves it in a Streamlit
dashboard deployed to a public URL. The live URL is the deliverable (resume/portfolio),
so the bar is "impressive in 10 seconds," not just "works."

## Architecture / data flow

```
data/generate_data.py      -> data/revenue_data.csv          (seeded synthetic data)
analysis/variance_engine.py -> calculate_variance(df, week)  -> structured dict
ai/narrative_engine.py      -> generate_narrative(summary)   -> Claude Opus 4.8 (structured output)
scripts/pregenerate.py      -> data/narratives_cache.json    (run once, committed)
app/dashboard.py            -> reads CSV + cache, renders     (the public app)
```

**Key design principle: the deployed app needs no API key.** Narratives are
pre-generated offline by `scripts/pregenerate.py` and committed as
`data/narratives_cache.json`. The dashboard reads that cache, so the public URL
can't burn an API key. `ai/narrative_engine.py` is the ONLY code that spends tokens,
and it runs locally — never on Streamlit Cloud.

## Module responsibilities

- **`data/generate_data.py`** — Seeded RNG (`np.random.default_rng(42)`), so the
  dataset and its planted anomalies are reproducible. 12 weeks × 4 lines = 48 rows.
  Planted anomalies: Wk4 Enterprise −22%, Wk5–6 Consulting +19%/+22% (a 2-week
  ahead-of-plan streak), Wk7 SMB +18%, Wk10 API −15%, Wk12 portfolio slightly below
  plan. Don't change the seed or anomalies without re-running pregenerate.
- **`analysis/variance_engine.py`** — Pure, stateless, pandas-only. `calculate_variance(df, week=None)`
  returns the canonical dict (`week`, `portfolio`, `product_lines{...}`, `anomalies[]`).
  Status is **direction-aware** (5 buckets): Ahead of Plan >+15%, Favorable +5–15%,
  On Track ±5%, At Risk −5–15%, Critical beyond −15%. The taxonomy
  (`STATUS_ORDER`/`STATUS_DEFINITIONS` + `classify_status()`) is the single source of
  truth — the dashboard colors/legend/signals and the narrative prompt all derive from it.
- **`ai/narrative_engine.py`** — Model `claude-opus-4-8`. Uses `client.messages.parse(...,
  output_format=ExecutiveNarrative)` (Pydantic) so the three sections come back as typed
  fields, not parsed text. Returns a fallback dict (never raises) on API failure.
- **`scripts/pregenerate.py`** — Loops all 12 weeks, writes the narrative cache. Run after
  any change to the data or the variance/prompt logic.
- **`app/dashboard.py`** — Streamlit. Wide layout, week selector, Run Analysis button,
  4 metric cards, Plotly grouped-bar + 12-week trend, color-coded status table, narrative
  cards from cache. A gated "Regenerate live" button appears only when an API key is present.

## Commands

```bash
# Use the `py` launcher on Windows (see gotcha below)
py data/generate_data.py                 # regenerate the dataset
py scripts/pregenerate.py                # regenerate narrative cache (needs ANTHROPIC_API_KEY in .env)
py -m streamlit run app/dashboard.py     # run the app locally
```

There is no test suite. To verify the dashboard without a browser, use Streamlit's
`AppTest` harness (`from streamlit.testing.v1 import AppTest`) and assert `at.exception`
is empty after `.run()` and after clicking the Run Analysis button.

## Conventions & gotchas

- **Windows: use `py`, not `python`.** The `python` command resolves to the Windows Store
  stub and fails intermittently. The real interpreter is Python 3.14 via the `py` launcher.
- **Console is cp1252.** Do not `print()` non-ASCII (em-dash, ✓, etc.) — it raises
  `UnicodeEncodeError`. Keep console/log strings ASCII. File writes use `encoding="utf-8"`,
  so non-ASCII in the data/cache/JSON is fine; only stdout is the constraint.
- **Streamlit:** use `width="stretch"`, not the deprecated `use_container_width=True`.
- **Model ID is exactly `claude-opus-4-8`** (no date suffix). Narrative quality is the
  showcase — don't downgrade the model to save cost; it's ~1 call per week.
- **After changing data or variance/prompt logic, re-run `scripts/pregenerate.py`** or the
  committed cache will be stale relative to the dashboard's live metrics.
- **Secrets:** `.env` (gitignored) holds `ANTHROPIC_API_KEY` for local generation only.
  Never commit it. The deployed app does not read it.

## Automation (built)

**n8n / scheduled automation is now built** — a self-hosted n8n container
(`n8n/`) runs the pipeline (read data -> variance -> narrative -> update cache ->
commit & push to `main`) on a schedule or on demand, so Streamlit Cloud redeploys
with no analyst running a script. See `n8n/README.md` and `n8n_workflow_spec.md`.

## Out of scope (documented as future work in README)

User CSV upload, DuckDB. Don't add these unless asked.
