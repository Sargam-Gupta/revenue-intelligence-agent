# Revenue Intelligence Agent — Project Specification

## What This Project Does

A fully automated revenue reporting agent that:
1. Reads weekly revenue data (actual vs. plan) across 4 product lines
2. Calculates variance metrics automatically (no manual Excel work)
3. Detects anomalies (significant misses or spikes vs. plan)
4. Sends the numbers to the Claude API, which writes an executive-ready narrative
5. Displays everything in a live, interactive Streamlit dashboard

**Target outcome:** What used to take a finance analyst 8+ hours of manual work (SQL pulls, Excel reconciliation, narrative writing) runs automatically in under 2 minutes.

---

## Tech Stack

| Layer | Tool | Purpose |
|-------|------|---------|
| Data | Python + Pandas | Generate and process revenue dataset |
| Analysis | Pandas / DuckDB | Calculate variance, WoW change, anomaly flags |
| AI Narrative | Claude API (claude-sonnet-4-6) | Generate exec-ready commentary |
| Automation | n8n | Schedule and orchestrate the pipeline |
| Dashboard | Streamlit + Plotly | Interactive web app with charts |
| Deployment | Streamlit Cloud + GitHub | Live public URL for portfolio |

---

## Project Folder Structure

Build the project with the following folder and file structure:

```
revenue-intelligence-agent/
│
├── data/
│   └── generate_data.py          # Script to create simulated revenue dataset
│   └── revenue_data.csv          # Output: the generated dataset
│
├── analysis/
│   └── variance_engine.py        # Calculates all variance metrics
│
├── ai/
│   └── narrative_engine.py       # Builds prompt + calls Claude API
│
├── app/
│   └── dashboard.py              # Streamlit web app
│
├── .env                          # API keys (never commit this to GitHub)
├── .gitignore                    # Must include .env
├── requirements.txt              # All Python dependencies
└── README.md                     # Project documentation
```

---

## Step 1: Generate the Dataset

**File:** `data/generate_data.py`

Create a Python script that generates a CSV file (`revenue_data.csv`) with the following structure:

### Required columns:
- `week_start_date` — Monday date for each week (12 weeks total, going backward from today)
- `product_line` — One of: `Enterprise`, `SMB`, `API`, `Consulting`
- `actual_revenue` — Actual revenue in USD for that week and product line
- `plan_revenue` — Planned revenue in USD for that week and product line

### Data requirements:
- 12 weeks × 4 product lines = 48 rows total
- Revenue ranges (plan baselines):
  - Enterprise: ~$180,000–$220,000/week
  - SMB: ~$90,000–$110,000/week
  - API: ~$45,000–$55,000/week
  - Consulting: ~$25,000–$35,000/week
- Add realistic variance: most weeks within ±8% of plan
- **Include these deliberate anomalies** (so the AI has something interesting to analyze):
  - Week 4: Enterprise misses plan by 22% (simulate a lost deal)
  - Week 7: SMB beats plan by 18% (simulate a campaign spike)
  - Week 10: API misses plan by 15% (simulate a churn event)
  - Most recent week (Week 12): overall portfolio slightly below plan (sets up a meaningful narrative)

### Output:
Save as `data/revenue_data.csv`. Also print a preview of the first 10 rows when the script runs so we can verify it looks correct.

---

## Step 2: Variance Calculation Engine

**File:** `analysis/variance_engine.py`

Create a Python module with a function called `calculate_variance(df)` that takes the revenue dataframe and returns a clean summary dictionary.

### The function must calculate:

**For each product line in the most recent week:**
- `actual` — actual revenue
- `plan` — planned revenue
- `variance_dollars` — actual minus plan
- `variance_pct` — variance as a percentage of plan, rounded to 1 decimal place
- `wow_change_pct` — week-over-week change vs. the previous week's actual, rounded to 1 decimal place
- `status` — `"On Track"` if within ±5%, `"At Risk"` if between ±5–15%, `"Critical"` if beyond ±15%

**For the overall portfolio (all product lines combined) in the most recent week:**
- Total actual revenue
- Total plan revenue
- Total variance in dollars and percentage
- Overall status flag

**4-week rolling trend per product line:**
- Direction: `"Improving"`, `"Declining"`, or `"Stable"` based on the last 4 weeks of actuals vs. plan

### Output format:
Return a Python dictionary structured like this:
```python
{
  "week": "2026-06-09",
  "portfolio": {
    "total_actual": 380000,
    "total_plan": 400000,
    "variance_dollars": -20000,
    "variance_pct": -5.0,
    "status": "At Risk"
  },
  "product_lines": {
    "Enterprise": {
      "actual": 190000,
      "plan": 200000,
      "variance_dollars": -10000,
      "variance_pct": -5.0,
      "wow_change_pct": 2.1,
      "status": "At Risk",
      "trend": "Declining"
    },
    # ... other product lines
  },
  "anomalies": [
    "Enterprise has declined for 3 consecutive weeks",
    "API variance exceeds -15% threshold — flagged as Critical"
  ]
}
```

---

## Step 3: AI Narrative Engine

**File:** `ai/narrative_engine.py`

Create a Python module with a function called `generate_narrative(variance_summary)` that takes the variance dictionary from Step 2, builds a structured prompt, calls the Claude API, and returns the narrative text.

### API setup:
- Use the `anthropic` Python library
- Model: `claude-sonnet-4-6`
- Load the API key from a `.env` file using `python-dotenv`
- Max tokens: 500 (narratives should be concise)

### Prompt structure:
The prompt sent to Claude must follow this exact structure:

```
System message:
"You are a senior FP&A analyst at a technology company. You write concise, 
accurate, and actionable revenue variance commentaries for executive audiences. 
Your output is always structured, data-specific, and free of filler language."

User message:
"Here is this week's revenue performance data:

PORTFOLIO SUMMARY
Week of: {week}
Total Actual Revenue: ${total_actual:,}
Total Plan Revenue: ${total_plan:,}
Total Variance: ${variance_dollars:,} ({variance_pct}%)
Portfolio Status: {status}

PRODUCT LINE BREAKDOWN
{for each product line: name, actual, plan, variance %, WoW change, status, trend}

ANOMALIES DETECTED
{list anomalies}

Based on this data, write the following — use specific numbers from the data above:

1. EXECUTIVE SUMMARY (3 sentences max): Overall portfolio performance this week, 
   the single biggest driver of variance, and the business implication.

2. TOP 3 DRIVERS (bullet points): The three most significant factors explaining 
   this week's performance. Be specific — use product line names and percentages.

3. RISK FLAG (1 sentence): The single most important trend or risk finance 
   leadership should watch next week.

Format your response with these exact three headers: 
EXECUTIVE SUMMARY, TOP 3 DRIVERS, RISK FLAG."
```

### Error handling:
- If the API call fails, return a fallback string: `"Narrative generation failed. Please check API key and connection."`
- Print a confirmation message when the API call succeeds: `"✓ Narrative generated successfully"`

---

## Step 4: Streamlit Dashboard

**File:** `app/dashboard.py`

Build a Streamlit web app that serves as the interactive front end for the entire tool.

### Page configuration:
- Page title: `"Revenue Intelligence Agent"`
- Layout: `"wide"`
- No sidebar needed

### Dashboard layout (top to bottom):

**Header section:**
- Main title: `"Revenue Intelligence Agent"`
- Subtitle: `"Automated weekly revenue variance analysis powered by AI"`
- A horizontal divider line

**Controls row:**
- A `st.selectbox` that lets the user pick which week to analyze (populated from the unique weeks in the dataset, most recent first)
- A button labeled `"Run Analysis"` — clicking this triggers the full pipeline

**On button click, display in order:**

1. **Portfolio metrics row** — 4 metric cards side by side using `st.columns(4)`:
   - Total Actual Revenue (formatted as $XXX,XXX)
   - Total Plan Revenue
   - Variance $ (colored red if negative, green if positive)
   - Variance % (colored red if negative, green if positive)

2. **Product line performance chart** — A Plotly grouped bar chart:
   - X-axis: product lines (Enterprise, SMB, API, Consulting)
   - Two bars per product line: Actual (blue) and Plan (gray)
   - Title: `"Actual vs. Plan by Product Line — Week of {date}"`
   - Clean, minimal styling

3. **Trend chart** — A Plotly line chart:
   - X-axis: all 12 weeks
   - One line per product line showing actual revenue over time
   - Plan shown as a dashed line for reference
   - Title: `"12-Week Revenue Trend by Product Line"`

4. **Product line status table** — A `st.dataframe` showing:
   - Columns: Product Line | Actual | Plan | Variance $ | Variance % | WoW Change | Status | Trend
   - Color-code the Status column: green for On Track, yellow for At Risk, red for Critical

5. **AI Narrative section:**
   - Section header: `"AI-Generated Executive Commentary"`
   - A subtle info box (`st.info`) with the text: `"Generated by Claude AI based on this week's variance data"`
   - Display the three narrative sections (Executive Summary, Top 3 Drivers, Risk Flag) in clean formatted text
   - A copy button if possible, or just clean readable formatting

6. **Footer:**
   - Small muted text: `"Built by Sargam Gupta · Revenue Intelligence Agent · Powered by Claude API"`

### Loading state:
- While the analysis is running, show `st.spinner("Running analysis and generating narrative...")`
- This makes it clear the tool is working, not frozen

---

## Step 5: Environment and Dependencies

### `.env` file (create this, never commit to GitHub):
```
ANTHROPIC_API_KEY=your_api_key_here
```

### `.gitignore` file:
```
.env
__pycache__/
*.pyc
.DS_Store
venv/
```

### `requirements.txt` — include all of these:
```
anthropic
streamlit
pandas
plotly
python-dotenv
duckdb
```

---

## Step 6: README.md

Write a clean, professional README with the following sections:

### Sections to include:

**Project title and one-line description**

**The Problem**
"Weekly revenue reporting at most companies requires 8+ hours of manual work: SQL pulls, Excel reconciliation, and narrative writing. Finance analysts spend more time assembling data than interpreting it."

**The Solution**
Describe what the agent does in 3-4 sentences.

**Architecture diagram** (text-based is fine):
```
Revenue Data (CSV)
      ↓
Variance Engine (Python/Pandas)
      ↓
Anomaly Detection
      ↓
Claude API (Prompt Engineering)
      ↓
Executive Narrative
      ↓
Streamlit Dashboard (Live Web App)
```

**Tech Stack** — reproduce the table from above

**How to Run Locally** — step by step:
1. Clone the repo
2. Install dependencies: `pip install -r requirements.txt`
3. Add your Anthropic API key to `.env`
4. Generate the dataset: `python data/generate_data.py`
5. Run the app: `streamlit run app/dashboard.py`

**Key Features** — bullet list of 5-6 highlights

**Project Context**
"Built as part of a Finance × AI portfolio to demonstrate applied AI development in a real FP&A context. Designed to mirror the kind of automated reporting infrastructure being built at companies like Snowflake, Google Cloud, and Qualcomm."

**Author** — Sargam Gupta, LinkedIn link placeholder

---

## Build Order for Claude Code

Execute in this exact sequence. Complete and verify each step before moving to the next.

1. Create the folder structure
2. Build and run `data/generate_data.py` → verify CSV looks correct
3. Build `analysis/variance_engine.py` → test it by printing the output dictionary
4. Set up `.env` with the Anthropic API key
5. Build `ai/narrative_engine.py` → test it standalone with one week of data
6. Build `app/dashboard.py` → run locally with `streamlit run app/dashboard.py`
7. Verify the full pipeline works end to end
8. Create `requirements.txt`, `.gitignore`, and `README.md`
9. Push to GitHub
10. Deploy to Streamlit Cloud

---

## What Success Looks Like

When the project is complete, you should be able to:

- Open the live Streamlit URL in any browser
- Select any week from the dropdown
- Click "Run Analysis"
- See the variance metrics, two charts, and a status table load instantly
- See the AI-generated narrative appear below — 3 structured sections with specific numbers from the data
- The whole process takes under 10 seconds

The live URL is what goes on the resume, LinkedIn, and portfolio website.
