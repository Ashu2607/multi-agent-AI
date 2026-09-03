"""Locust load test (M6 Step 6 / Category 5 evidence).

Category 5 requires a real 500-user run against this repo's own
VM-hosted Docker Compose stack - not Cloud Run (Category 3 is a
light-touch deploy/verify target, not a load-test target; a $10 total
GCP credit budget doesn't survive 500 concurrent users hitting a
billed-per-request service). Run this from inside the VM's own SSH
session, Compose stack already up, pointed at the Compose-exposed
backend port:

    pip install locust   # (or: pip install -r requirements.txt)
    API_KEY=... DEMO_USERNAME=demo DEMO_PASSWORD=... \\
      python -m locust -f scripts/locustfile.py --headless \\
      -u 500 -r 20 -t 60s --host=http://localhost:8000 \\
      --csv=reports/load_test

`python -m locust`, not bare `locust` - pip installs it to a user bin dir
that isn't always on PATH; running it as a module sidesteps that.

Read the `95%` column off the `/research` row in
`reports/load_test_stats.csv` - that's the P95 for the Model Card.
A real 500-user run that shows failures because the app's own OpenAI key
hit its rate limit is an expected, documented pass, not something to
hide or rerun until it looks clean - see the shared Category 5 grading
note. What matters is a real number plus a correct diagnosis of any
failures, not a suspiciously perfect one.
"""
from __future__ import annotations

import os
import random

from locust import HttpUser, between, task

API_KEY = os.environ.get("API_KEY", "")
DEMO_USERNAME = os.environ.get("DEMO_USERNAME", "demo")
DEMO_PASSWORD = os.environ.get("DEMO_PASSWORD", "")

# A rotating pool of realistic research tasks rather than one repeated
# query, so the run reflects varied pipeline paths (web/SQL/knowledge-base
# routing) instead of one cached-looking shape.
SAMPLE_TASKS = [
    "How many products do we have in the catalog?",
    "Summarize our top competitors from the market research report.",
    "What are the current customer support policies for refunds?",
    "Give me a quarterly sales summary for the last quarter.",
    "What does the product manual say about enterprise AI features?",
    "Compare our pricing against competitors.",
]


class ResearchUser(HttpUser):
    wait_time = between(1, 3)

    def on_start(self):
        """Log in once per simulated user and cache both required auth
        headers for every request after (JWT + API key, both required on
        every /research* route - see app/auth.py)."""
        resp = self.client.post(
            "/auth/login",
            json={"username": DEMO_USERNAME, "password": DEMO_PASSWORD},
            headers={"X-API-Key": API_KEY},
        )
        token = resp.json().get("access_token", "")
        self.client.headers.update({"X-API-Key": API_KEY, "Authorization": f"Bearer {token}"})

    @task
    def ask_research(self):
        task_text = random.choice(SAMPLE_TASKS)
        self.client.post("/research", json={"task": task_text}, name="/research")
