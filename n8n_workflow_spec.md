# n8n Automation Workflow — Build Specification (v2, codebase-accurate)

## What This Adds to the Project

The Revenue Intelligence Agent dashboard reads pre-generated narratives from a
committed cache (`data/narratives_cache.json`). This n8n workflow is the
automation layer that runs the real pipeline — read data → calculate variance →
call Claude → update the cache → **commit & push** — so the public Streamlit
Cloud app updates without anyone manually running scripts.

It makes the word "automated" in the project description literally true: because
Node 5 pushes to GitHub, and Streamlit Cloud redeploys on push, a workflow run
actually changes the live URL.

> **Honesty note for the case study:** the underlying dataset is *seeded
> synthetic* data, not a live feed. In production, Node 2 would pull from a data
> warehouse; here it reads the committed CSV. We say this plainly rather than
> implying a real data source.

---

## Decisions Locked (from review)

1. **Runtime:** self-hosted n8n locally via **Docker**.
2. **Goal:** honest demo — the workflow runs the *real* pipeline; for the
   recording it is triggered manually ("Execute Workflow"), not left to the timer.
3. **Output reach:** Node 5 does `git commit && git push`, so the **deployed**
   Streamlit Cloud app updates (not just a local cache).
4. **Granularity:** five genuine stages — each node calls a real CLI, so nodes
   are independent steps, not cosmetic wrappers around one script.

---

## Architecture Concept

n8n sits **above** the existing pipeline as an orchestrator. It does not
reimplement any Python logic — it sequences the existing scripts and adds the
publish (git) step.

```
        ┌──────────────────────────────────────────────────────────┐
        │                     n8n (Orchestrator)                    │
        │  Trigger → Read → Variance → Narrative → Publish(git push) │
        └──────────────────────────────────────────────────────────┘
                                   │
                                   ▼
   Revenue CSV → variance_engine.py → narrative_engine.py → cache + git push
   (read-only)     (--week latest)      (--input variance)   (→ Streamlit Cloud redeploys)
```

---

## Prerequisite: Execution Environment (do this first)

The stock `n8nio/n8n` image is Alpine and ships **no Python, no project
dependencies, and no git wiring**. The Execute Command nodes run inside the n8n
container, so that container must have everything the pipeline needs.

### Custom image + compose

`n8n/Dockerfile`:
```dockerfile
FROM n8nio/n8n:latest
USER root
RUN apk add --no-cache python3 py3-pip git
# Project deps. Modern numpy/pandas ship musllinux wheels, so no compiler needed.
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --break-system-packages -r /tmp/requirements.txt
USER node
```

`n8n/docker-compose.yml`:
```yaml
services:
  n8n:
    build: ./n8n
    ports:
      - "5678:5678"
    environment:
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}   # for Node 4 (Claude call)
      - GH_TOKEN=${GH_TOKEN}                      # fine-grained PAT for Node 5 push
      - GIT_AUTHOR_NAME=Sargam Gupta
      - GIT_AUTHOR_EMAIL=107276370+Sargam-Gupta@users.noreply.github.com
      - GIT_COMMITTER_NAME=Sargam Gupta
      - GIT_COMMITTER_EMAIL=107276370+Sargam-Gupta@users.noreply.github.com
    volumes:
      - ./n8n/data:/home/node/.n8n        # n8n's own state
      - ..:/repo                          # the project repo, mounted read-write
```

Notes:
- Inside the container the interpreter is **`python3`** (Linux), not the `py`
  launcher you use on Windows. All node commands below use `python3` and run
  from `/repo`.
- The repo is mounted at `/repo`, so the container operates on your actual
  working tree and can push real commits.
- **Secrets:** `ANTHROPIC_API_KEY` and `GH_TOKEN` come from a local `.env` next
  to the compose file (gitignored) or from n8n credentials — never hardcoded in
  a node. The `GH_TOKEN` must be a **fresh fine-grained PAT** scoped to *only*
  this repo with **Contents: read/write** (the token pasted in chat earlier is
  burned — revoke it). This does reintroduce a key into the automation host;
  that's acceptable because the host is your local machine, self-hosted.

---

## Code Changes Required First (thin CLIs)

Each node needs a real command-line entry point. These are small, additive
`argparse` wrappers around logic that already exists — no behavior change to the
functions themselves. Scratch hand-off files live in `/repo/run/` (gitignored).

| File | New CLI | Behavior |
|---|---|---|
| `data/generate_data.py` | `--ensure` | Generate the CSV only if missing; otherwise read it, print row count + latest week ISO, and **do not overwrite** (so weekly runs don't shift the date keys). |
| `analysis/variance_engine.py` | `--week {iso\|latest}` `--out FILE` | Compute the variance dict for the week (default `latest`); write JSON to `--out` (default stdout). The dict already includes `week`, so the target week travels downstream inside the JSON. |
| `ai/narrative_engine.py` | `--input FILE` `--out FILE` | Read a variance JSON (default stdin), call `generate_narrative`, write the narrative dict JSON to `--out` (default stdout). Reuses the exact tested prompt — no drift. |
| `scripts/update_cache.py` (new) | `--variance FILE` `--narrative FILE` | Merge **one** week's narrative into `data/narratives_cache.json`, preserving the other 11 entries. Reads the week key from the variance JSON. Writes utf-8. Prints which week changed. |

Add to `.gitignore`: `run/` and `n8n/data/`.

> The existing `scripts/pregenerate.py` (all-weeks regen) stays as-is for a full
> rebuild; the workflow updates a single week incrementally.

---

## The 5 Nodes

Exactly five, no branching, no notifications, no retry nodes (see "What NOT to
Build"). Commands run with working directory `/repo`.

### Node 1 — Schedule Trigger
- Type: **Schedule Trigger**
- Frequency: weekly, Monday 08:00. For the demo recording you fire it manually
  via **Execute Workflow**; the schedule is shown but not waited on.

### Node 2 — Read / Validate Data (data layer)
- Type: **Execute Command**
- Command: `cd /repo && python3 data/generate_data.py --ensure`
- Reads the committed CSV, confirms 48 rows / 12 weeks, prints the latest week.
  Does **not** regenerate (regenerating would shift every `week_start_date` and
  invalidate the 11 cached narratives Node 4 doesn't touch).

### Node 3 — Run Variance Engine (analysis layer)
- Type: **Execute Command**
- Command: `cd /repo && python3 analysis/variance_engine.py --week latest --out run/variance.json`
- Produces the variance summary (variance $, %, status, trend, anomalies, and
  the `week` key) as JSON for the next node. Same logic the dashboard uses — not
  duplicated in n8n.

### Node 4 — Generate Narrative via Claude (AI layer)
- Type: **Execute Command**
- Command: `cd /repo && python3 ai/narrative_engine.py --input run/variance.json --out run/narrative.json`
- Calls Claude **through the existing Python** (`messages.parse` + the Pydantic
  schema), so the structured-output prompt can't drift from the app version.
  Reads `ANTHROPIC_API_KEY` from the container env.
- **Why not an HTTP Request node:** a raw POST to `/v1/messages` would have to
  re-implement the structured-output parsing and re-declare headers
  (`anthropic-version`, `content-type`) — exactly the drift risk we're avoiding.
  The HTTP approach is mentioned in interviews as "the alternative we
  deliberately didn't take," not built.

### Node 5 — Update Cache & Publish (output layer)
- Type: **Execute Command**
- Command (single compound command):
  ```
  cd /repo \
   && python3 scripts/update_cache.py --variance run/variance.json --narrative run/narrative.json \
   && git add data/narratives_cache.json \
   && git commit -m "Auto: refresh narrative for $(python3 analysis/variance_engine.py --week latest --out /dev/stdout | python3 -c 'import sys,json;print(json.load(sys.stdin)["week"])')" \
   && git push "https://x-access-token:${GH_TOKEN}@github.com/Sargam-Gupta/revenue-intelligence-agent.git" main
  ```
  (Simpler/cleaner: have `update_cache.py` print the week and use a fixed commit
  message like `Auto: refresh weekly narrative cache`. Keep the commit touching
  **only** `data/narratives_cache.json` so the diff is one file — easy to show in
  the Loom.)
- Streamlit Cloud watches the repo and redeploys on push, so the live app
  reflects the new narrative within a minute or two — no manual reboot.

---

## Build Order

1. Build the custom image and bring up n8n: `docker compose -f n8n/docker-compose.yml up -d --build`. Confirm `http://localhost:5678` loads.
2. Add the four CLIs (table above) and test each **on the host** first:
   `py analysis/variance_engine.py --week latest --out run/variance.json`, etc.
   Confirm `run/variance.json` and `run/narrative.json` look right and
   `update_cache.py` preserves all 12 weeks.
3. Node 1 (Schedule Trigger) — set weekly; verify it appears active.
4. Node 2 → run it; confirm it prints the latest week and doesn't rewrite the CSV.
5. Node 3 → confirm `run/variance.json` matches the dashboard's numbers.
6. Node 4 → first run against a checked-in sample `run/variance.json` in
   isolation to confirm the Claude call + parse works, then wire it to Node 3.
7. Node 5 → confirm the cache merges (only the latest week changes), the commit
   touches one file, the push lands, and the **deployed** app updates.
8. Run the whole workflow end-to-end via **Execute Workflow**.
9. Capture deliverables (below) after a clean green run.

---

## What NOT to Build

- No Slack/email notification nodes.
- No conditional/branching logic ("if Critical, alert") — mention as a future
  enhancement verbally.
- No retry/error-handling nodes — mention as "production hardening."
- No HTTP Request node for Claude — the Execute Command path reuses the tested
  prompt; the HTTP version is the deliberately-not-taken alternative.

---

## Deliverables for the Portfolio Case Study

1. **Static screenshot** of the 5-node canvas, clean, ideally after a successful
   run (green checks on each node).
2. **Short Loom (15–30s)** of the workflow executing via Execute Workflow, each
   node going green — and, as the payoff, the GitHub commit appearing / the live
   app updating.
3. **One-sentence business framing** (now literally true):
   "This n8n workflow makes the weekly reporting fully autonomous — it reads the
   week's data, runs the variance analysis, generates the executive narrative
   with Claude, updates the dashboard cache, and pushes it live, with no analyst
   running a script."

---

## How This Fits the Case Study Page

1. Architecture diagram: n8n as orchestrator **above** the 4-layer pipeline.
2. The 5-node canvas screenshot, one-line caption per node.
3. The embedded Loom link.
4. The one-sentence impact framing above.

n8n stays proportionate — the dashboard and narrative quality remain the
centerpiece; n8n is the proof it's automated end-to-end.

---

## Open Notes / Risks

- **Token hygiene:** the `GH_TOKEN` lives only in the local `.env` / n8n
  credentials. Use a fresh fine-grained PAT scoped to this one repo; revoke the
  token exposed earlier in chat.
- **Date-key stability:** the weekly path intentionally never calls
  `generate_data.py` without `--ensure`, because regenerating shifts every
  `week_start_date` and would orphan the other 11 cached narratives.
- **Docs:** `CLAUDE.md` currently lists n8n under "Out of scope (future work)."
  Once this is built, flip that line (and the README) so the docs match the repo.
- **Windows vs container:** host commands use the `py` launcher; the in-container
  node commands use `python3`. Don't copy one into the other.
