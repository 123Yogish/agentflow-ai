import os
import tempfile
import unittest

DB_FILE = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
DB_FILE.close()
os.environ["DATABASE_PATH"] = DB_FILE.name
os.environ.pop("OPENAI_API_KEY", None)

import app as agentflow

class AgentFlowApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        agentflow.app.config.update(TESTING=True)
        cls.client = agentflow.app.test_client()

    def test_health_and_agent_roster(self):
        self.assertEqual(self.client.get("/health").json["status"], "ok")
        data = self.client.get("/api/agents").json
        self.assertEqual(len(data["agents"]), 4)
        self.assertEqual(data["mode"], "demo")

    def test_demo_run_returns_four_completed_steps_and_persists(self):
        response = self.client.post("/api/runs", json={"prompt": "Plan an onboarding experiment for a new team app"})
        self.assertEqual(response.status_code, 201)
        run = response.json["run"]
        self.assertEqual(run["status"], "completed")
        self.assertEqual(run["mode"], "demo")
        self.assertEqual(len(run["steps"]), 4)
        self.assertTrue(all(step["status"] == "completed" for step in run["steps"]))
        saved = self.client.get(f"/api/runs/{run['id']}")
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json["run"]["title"], run["title"])

    def test_prompt_validation_and_missing_run(self):
        self.assertEqual(self.client.post("/api/runs", json={"prompt": "short"}).status_code, 400)
        self.assertEqual(self.client.post("/api/runs", json={"prompt": "x" * 4001}).status_code, 400)
        self.assertEqual(self.client.get("/api/runs/no-such-run").status_code, 404)

    @classmethod
    def tearDownClass(cls):
        try:
            os.unlink(DB_FILE.name)
        except OSError:
            pass

if __name__ == "__main__":
    unittest.main()
