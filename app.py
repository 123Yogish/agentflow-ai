import json
import os
import sqlite3
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

from flask import Flask, jsonify, render_template, request

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("DATABASE_PATH", BASE_DIR / "agentflow.db"))
app = Flask(__name__)
app.config["JSON_SORT_KEYS"] = False

AGENTS = [
    {"id": "planner", "name": "Orchestrator", "role": "Breaks the request into clear objectives and assigns work.", "color": "violet", "icon": "✳"},
    {"id": "researcher", "name": "Researcher", "role": "Surfaces context, constraints, and useful evidence.", "color": "blue", "icon": "⌕"},
    {"id": "builder", "name": "Builder", "role": "Turns the plan into a concrete, structured deliverable.", "color": "green", "icon": "⌘"},
    {"id": "reviewer", "name": "Reviewer", "role": "Checks the result for gaps and actionable improvements.", "color": "amber", "icon": "✓"},
]

@contextmanager
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS runs (
            id TEXT PRIMARY KEY, title TEXT NOT NULL, prompt TEXT NOT NULL,
            status TEXT NOT NULL, mode TEXT NOT NULL, created_at TEXT NOT NULL,
            result TEXT, duration_ms INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS steps (
            id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL,
            agent_id TEXT NOT NULL, status TEXT NOT NULL, content TEXT,
            duration_ms INTEGER DEFAULT 0, created_at TEXT NOT NULL,
            FOREIGN KEY(run_id) REFERENCES runs(id)
        );
        """)
        if conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 0:
            seed_demo(conn)

def now():
    return datetime.now(timezone.utc).isoformat()

def seed_demo(conn):
    rid = "demo-agentflow-launch"
    prompt = "Design a launch plan for an AI meeting-notes assistant for small product teams. Include a clear audience, positioning, first-month experiments, and success metrics."
    outputs = [
        "Objective: create a focused four-week launch plan. Audience: 5–30 person product teams that need decisions and owners captured without adding another meeting. Deliverables: positioning, experiments, and measurable targets.",
        "Useful constraints: earn trust with visible source links, make editing faster than rewriting, and fit existing tools. Initial assumption: target teams already use video calls and a shared project tracker. Validate willingness to pay before expanding integrations.",
        "Positioning: ‘Meeting decisions, ready for your team’s next step.’\n\nWeek 1 — Interview 8 product leads; test a clickable notes-to-actions flow.\nWeek 2 — Run a concierge pilot with 3 teams; measure edits and follow-through.\nWeek 3 — Publish 2 short product demos and invite 20 design partners.\nWeek 4 — Convert engaged pilots to paid trials; document security questions.\n\nMetrics: 10 qualified teams, 3 active pilots, ≥60% action-item acceptance, ≥3 weekly returning teams, and 2 paid trial commitments.",
        "Review: the plan has a narrow audience, staged experiments, and measurable outcomes. Add a consent and data-retention checklist before recording real meetings. Replace the 60% acceptance target after establishing a baseline with the first pilot."
    ]
    conn.execute("INSERT INTO runs VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (rid, "Meeting notes launch plan", prompt, "completed", "demo", now(), outputs[-1], 2180))
    for agent, content in zip(AGENTS, outputs):
        conn.execute("INSERT INTO steps(run_id,agent_id,status,content,duration_ms,created_at) VALUES(?,?,?,?,?,?)", (rid, agent["id"], "completed", content, 400 + len(content) * 2, now()))

def local_output(agent_id, prompt, prior):
    topic = prompt.strip().rstrip(".")
    if agent_id == "planner":
        return f"Objective: address “{topic}”.\n\nI’ll clarify the outcome, identify the audience and constraints, then produce a practical first version and check it for gaps. The researcher will surface assumptions; the builder will draft the deliverable; the reviewer will check quality and next steps."
    if agent_id == "researcher":
        return "Context and assumptions\n• Keep the first version focused on one primary user and one outcome.\n• Separate confirmed facts from assumptions; validate the highest-risk assumption early.\n• Prefer a small, observable experiment over a broad feature set.\n\nOpen question: which success signal matters most to the requester?"
    if agent_id == "builder":
        return f"## Working deliverable\n\n**Goal:** {topic}\n\n1. Define the primary user and the problem they need solved.\n2. Create the smallest end-to-end experience that delivers the outcome.\n3. Test it with a small group and collect direct feedback.\n4. Improve the weakest step, then expand access.\n\n**Success signals:** activation, repeat use, task completion, and user-reported value. Set numeric targets after establishing a baseline.\n\n**Next step:** choose the first user group and schedule a short validation session."
    return "Quality review\n\nThe draft gives a usable sequence and measurable signal categories. Before acting, specify the target audience, numeric baseline, owner, and deadline. Validate the key assumption with real users; avoid treating early feedback as proof of broad demand.\n\n**Status:** Ready for a focused first validation, with the audience and targets to be confirmed."

def openai_output(agent, prompt, prior):
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        return None
    context = "\n\nPrior team notes:\n" + "\n".join(f"{a}: {t}" for a, t in prior) if prior else ""
    body = {"model": os.environ.get("OPENAI_MODEL", "gpt-4o-mini"), "messages": [
        {"role": "system", "content": f"You are {agent['name']}, a specialist in a collaborative multi-agent product team. Role: {agent['role']} Be concise, concrete, and clearly label assumptions. Build on earlier agents' notes.{context}"},
        {"role": "user", "content": prompt}], "temperature": 0.5}
    req = Request("https://api.openai.com/v1/chat/completions", data=json.dumps(body).encode(), headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, method="POST")
    with urlopen(req, timeout=90) as response:
        data = json.loads(response.read())
    return data["choices"][0]["message"]["content"].strip()

def as_run(row, include_steps=False):
    item = dict(row)
    if item.get("result"):
        try: item["result"] = json.loads(item["result"])
        except (TypeError, json.JSONDecodeError): pass
    if include_steps:
        with db() as conn:
            item["steps"] = [dict(s) for s in conn.execute("SELECT * FROM steps WHERE run_id=? ORDER BY id", (item["id"],)).fetchall()]
    return item

@app.get("/")
def index():
    return render_template("index.html")

@app.get("/api/agents")
def list_agents():
    return jsonify({"agents": AGENTS, "mode": "openai" if os.environ.get("OPENAI_API_KEY") else "demo"})

@app.get("/api/runs")
def list_runs():
    with db() as conn:
        rows = conn.execute("SELECT * FROM runs ORDER BY created_at DESC LIMIT 50").fetchall()
    return jsonify({"runs": [as_run(row) for row in rows]})

@app.get("/api/runs/<run_id>")
def get_run(run_id):
    with db() as conn:
        row = conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
    if not row: return jsonify({"error": "Run not found"}), 404
    return jsonify({"run": as_run(row, True)})

@app.post("/api/runs")
def create_run():
    payload = request.get_json(silent=True) or {}
    prompt = str(payload.get("prompt", "")).strip()
    if len(prompt) < 8: return jsonify({"error": "Add a little more detail (at least 8 characters)."}), 400
    if len(prompt) > 4000: return jsonify({"error": "Keep the request under 4,000 characters."}), 400
    rid, started, mode = uuid.uuid4().hex, time.perf_counter(), "openai" if os.environ.get("OPENAI_API_KEY") else "demo"
    title = str(payload.get("title", "")).strip()[:80] or prompt.splitlines()[0][:72]
    with db() as conn:
        conn.execute("INSERT INTO runs(id,title,prompt,status,mode,created_at) VALUES(?,?,?,?,?,?)", (rid, title, prompt, "running", mode, now()))
    previous = []
    try:
        for agent in AGENTS:
            step_started = time.perf_counter()
            with db() as conn:
                conn.execute("INSERT INTO steps(run_id,agent_id,status,created_at) VALUES(?,?,?,?)", (rid, agent["id"], "running", now()))
                step_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            output = openai_output(agent, prompt, previous) if mode == "openai" else None
            if output is None: output = local_output(agent["id"], prompt, previous)
            previous.append((agent["name"], output))
            with db() as conn:
                conn.execute("UPDATE steps SET status='completed',content=?,duration_ms=? WHERE id=?", (output, int((time.perf_counter()-step_started)*1000), step_id))
        elapsed = int((time.perf_counter()-started)*1000)
        with db() as conn:
            conn.execute("UPDATE runs SET status='completed',result=?,duration_ms=? WHERE id=?", (json.dumps(previous[-1][1]), elapsed, rid))
            row = conn.execute("SELECT * FROM runs WHERE id=?", (rid,)).fetchone()
        return jsonify({"run": as_run(row, True)}), 201
    except Exception as exc:
        with db() as conn:
            conn.execute("UPDATE runs SET status='failed',result=?,duration_ms=? WHERE id=?", (json.dumps(str(exc)), int((time.perf_counter()-started)*1000), rid))
            conn.execute("UPDATE steps SET status='failed',content=? WHERE run_id=? AND status='running'", (str(exc), rid))
            row = conn.execute("SELECT * FROM runs WHERE id=?", (rid,)).fetchone()
        return jsonify({"error": "The agent run could not finish. Check your provider configuration and try again.", "run": as_run(row, True)}), 502

@app.get("/health")
def health(): return jsonify({"status": "ok"})

init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=os.environ.get("FLASK_DEBUG") == "1")
