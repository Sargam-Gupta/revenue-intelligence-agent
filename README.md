# Revenue Intelligence Agent

**Automated weekly revenue variance analysis with AI-generated executive commentary.**

A finance-grade reporting agent that reads actual-vs-plan revenue across four
product lines, computes variance and anomaly metrics, asks Claude to write the
executive narrative, and serves it all in a live, interactive dashboard.

> What used to take a finance analyst 8+ hours of SQL pulls, Excel reconciliation,
> and narrative writing runs here in under two minutes.

## The Problem

Weekly revenue reporting at most companies requires 8+ hours of manual work: SQL
pulls, Excel reconciliation, and narrative writing. Finance analysts spend more
time assembling data than interpreting it.

## The Solution

This agent automates the entire loop. It ingests weekly revenue data, calculates
every variance metric (actual vs. plan, week-over-week, 4-week trend) and flags
anomalies automatically. It then sends the structured numbers to the Claude API,
which writes a concise, executive-ready commentary — an executive summary, the top
three drivers, and a forward-looking risk flag. Everything renders in an
interactive Streamlit dashboard where you select a week and get the full analysis
instantly.

## Architecture

```
Revenue Data (CSV)
      |
Variance Engine (Python / Pandas)
      |
Anomaly Detection
      |
Claude API (Opus 4.8, structured output)
      |
Executive Narrative  --cached-->  narratives_cache.json
      |
Streamlit Dashboard (Live Web App)
```

The Claude call happens **once**, offline, via `scripts/pregenerate.py`, which
caches every week's narrative to disk. The deployed dashboard serves that cache,
so the public app needs no API key and spends no tokens — strangers can't run up
a bill. A gated "regenerate live" control appears only when a key is present
locally.

## Tech Stack

| Layer        | Tool                         | Purpose                                            |
|--------------|------------------------------|----------------------------------------------------|
| Data         | Python + Pandas + NumPy      | Generate and process the revenue dataset           |
| Analysis     | Pandas                       | Variance, WoW change, trend, anomaly flags         |
| AI Narrative | Claude API (`claude-opus-4-8`) | Executive commentary via structured output       |
| Dashboard    | Streamlit + Plotly           | Interactive web app with charts                    |
| Deployment   | Streamlit Cloud + GitHub     | Live public URL                                    |

## How to Run Locally

```bash
# 1. Clone
git clone <your-repo-url>
cd revenue-intelligence-agent

# 2. Install dependencies
pip install -r requirements.txt

# 3. Generate the dataset
python data/generate_data.py

# 4. (Optional) regenerate the AI narratives — needs an API key
cp .env.example .env          # then edit .env and add ANTHROPIC_API_KEY
python scripts/pregenerate.py # writes data/narratives_cache.json

# 5. Run the app
streamlit run app/dashboard.py
```

Steps 3–4 are only needed if you want to rebuild the data or narratives; the repo
ships with both committed, so step 5 works out of the box.

## Key Features

- **Zero-key public deployment** — narratives are pre-generated and cached, so the
  live app is safe to share without exposing or burning an API key.
- **Structured AI output** — Claude returns typed JSON (summary / drivers / risk),
  rendered as clean sections instead of fragile text parsing.
- **Real anomaly detection** — Critical-threshold breaches and multi-week declines
  are detected programmatically and fed to the model, so the narrative is grounded
  in the data.
- **Any-week analysis** — one variance function powers the week selector across all
  12 weeks, not just the latest.
- **Reproducible data** — a seeded generator produces the same realistic dataset
  (with planted anomalies) on every machine.
- **Executive-ready visuals** — grouped actual-vs-plan bars, a 12-week trend with
  plan reference lines, and a color-coded status table.

## Project Context

Built as part of a Finance × AI portfolio to demonstrate applied AI development in
a real FP&A context. Designed to mirror the kind of automated reporting
infrastructure being built at companies like Snowflake, Google Cloud, and Qualcomm.

## Future Work

- Scheduled regeneration (n8n or GitHub Actions) for a true weekly cadence.
- User CSV upload to analyze real actual-vs-plan data.
- Drill-down by region / segment.

## Author

**Sargam Gupta** — [LinkedIn](https://www.linkedin.com/in/sargam-gupta-duke-uol/)
