# n8n Automation (self-hosted, Docker)

The orchestration layer for the Revenue Intelligence Agent. n8n runs the existing
Python pipeline on a schedule (or on demand) and publishes the result, so the
public Streamlit Cloud app updates with no analyst running a script.

See `../n8n_workflow_spec.md` for the full design rationale.

## Prerequisites

- **Docker Desktop** installed and running.
- `n8n/.env` created from `.env.example` with real `ANTHROPIC_API_KEY` (Node 4)
  and `GH_TOKEN` (Node 5). `.env` is gitignored.

## Bring it up

```bash
cp n8n/.env.example n8n/.env        # then edit in your real keys
docker compose -f n8n/docker-compose.yml up -d --build
# open http://localhost:5678
```

The custom image (`Dockerfile`) extends `n8nio/n8n` with `python3`, `git`, and the
pipeline deps (`requirements-pipeline.txt`). The repo is bind-mounted at `/repo`,
so the nodes run the real scripts and Node 5 pushes a real commit.

For the live demo, have this repo checked out on a clean `main` — Node 5 commits
the cache update on the current branch and pushes it to remote `main`.

## The 5 nodes

All command nodes are **Execute Command** type, running in the container
(`python3`, not the Windows `py` launcher). Scratch JSON lands in `/repo/run/`
(gitignored).

| # | Node | Type | Command |
|---|---|---|---|
| 1 | Schedule Trigger | Schedule Trigger | weekly, Mon 08:00 (fire manually via **Execute Workflow** for the recording) |
| 2 | Read / validate data | Execute Command | `cd /repo && python3 data/generate_data.py --ensure` |
| 3 | Variance | Execute Command | `cd /repo && python3 analysis/variance_engine.py --week latest --out run/variance.json` |
| 4 | Narrative (Claude) | Execute Command | `cd /repo && python3 ai/narrative_engine.py --input run/variance.json --out run/narrative.json` |
| 5 | Update cache & publish | Execute Command | see below |

Node 5 command (single Execute Command; `|| true` so an unchanged cache doesn't
hard-fail the node):

```bash
cd /repo \
 && python3 scripts/update_cache.py --variance run/variance.json --narrative run/narrative.json \
 && git add data/narratives_cache.json \
 && (git commit -m "Auto: refresh weekly narrative cache" || true) \
 && git push "https://x-access-token:${GH_TOKEN}@github.com/Sargam-Gupta/revenue-intelligence-agent.git" HEAD:main
```

Streamlit Cloud watches the repo and redeploys on push, so the live app reflects
the new narrative within a minute or two — no manual reboot.

## Smoke test without n8n

You can run the same chain inside the container directly to confirm the image is
wired correctly before building the canvas:

```bash
docker compose -f n8n/docker-compose.yml exec n8n sh -c '
  cd /repo &&
  python3 data/generate_data.py --ensure &&
  python3 analysis/variance_engine.py --week latest --out run/variance.json &&
  python3 ai/narrative_engine.py --input run/variance.json --out run/narrative.json &&
  python3 scripts/update_cache.py --variance run/variance.json --narrative run/narrative.json
'
```

(Stops before the git push, so it is safe to run repeatedly.)

## Deliverables for the case study

1. Clean screenshot of the 5-node canvas after a successful run (green checks).
2. 15–30s Loom of **Execute Workflow**, ending on the new GitHub commit / updated
   live app.
3. One sentence: "This n8n workflow makes the weekly reporting fully autonomous —
   it reads the week's data, runs the variance analysis, generates the executive
   narrative with Claude, updates the dashboard cache, and pushes it live, with no
   analyst running a script."
