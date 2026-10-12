# AgentFlow AI

AgentFlow is a full-stack multi-agent workspace that turns a user request into a visible, reviewable team run. An Orchestrator plans the work, a Researcher surfaces assumptions, a Builder creates the deliverable, and a Reviewer checks it. Every run and step is saved in SQLite and is available through the API and dashboard.

## Features

- Responsive workspace dashboard with agent roster, workflow status, activity history, and run details.
- Four role-based agents that pass earlier work forward in sequence.
- Built-in deterministic demo mode; no API key is needed to run the project.
- Optional OpenAI chat completions integration configured through environment variables.
- SQLite persistence, input validation, health endpoint, and error reporting.
- Seeded launch-plan run for an immediate product demo.

## Run locally

Requires Python 3.10 or newer.

```bash
python -m venv .venv
# Windows PowerShell
.venv\Scripts\Activate.ps1
# macOS / Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000. The first launch creates `agentflow.db` and seeds a sample run. To use live OpenAI responses, set `OPENAI_API_KEY` in your shell (and optionally `OPENAI_MODEL`, default `gpt-4o-mini`) before starting the app. Keep secrets out of Git.

## Verify

```bash
python -m unittest discover -s tests -v
```

The tests cover the health endpoint, agent roster, complete persisted demo run, request validation, and missing-run handling.

## API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health` | Platform health check |
| GET | `/api/agents` | Agent roster and active mode |
| GET | `/api/runs` | Most recent runs |
| POST | `/api/runs` | Execute a team run with `{ "prompt": "...", "title": "..." }` |
| GET | `/api/runs/<id>` | Run metadata and ordered agent steps |

## GitHub

The source is published at https://github.com/123Yogish/agentflow-ai. Keep `.env`, API keys, and the local database out of Git.

## Deploy on Render

This repository includes `render.yaml` for a free Render web service. Connect the GitHub repository in Render and create the service from the Blueprint. The Blueprint installs dependencies, starts Gunicorn, checks `/health`, and stores the demo SQLite database in `/tmp`. The free service sleeps when idle, and local files are ephemeral, so saved demo runs reset after a restart or redeploy. This makes it suitable for a portfolio preview, not durable user data. Add `OPENAI_API_KEY` in the service environment to enable provider-backed agents; without it the deployed app remains usable in demo mode. OpenAI API usage can incur separate charges. After deployment, use the Render service URL as the live demo link.

For other Python hosts, install `requirements.txt`, set `DATABASE_PATH` to a durable mounted-volume location, optionally set the OpenAI variables, and run `gunicorn app:app --workers 1 --threads 4 --timeout 120`. SQLite requires persistent storage and a single worker process; move to Postgres before scaling workers or running multiple replicas.

## Demo walkthrough

1. Open the dashboard and inspect the seeded “Meeting notes launch plan” run.
2. Submit a specific goal in the prompt box.
3. Watch each agent’s contribution and open the completed run from Recent runs.
4. Configure an API key and restart to show provider-backed collaboration.

The dashboard is a product demonstration, not a claim of real-time external research: the built-in Researcher organizes context and assumptions from the prompt. Connect an actual search provider before presenting it as web research.
