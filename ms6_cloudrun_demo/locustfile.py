# locustfile.py -- M6 load test, SIMPLIFIED (Cloud-Run-only redesign, 13 Aug
# evening). Client-facing goal is "knowledge level" -- show you understand
# how to run a load test and read a P95, not survive a stress test. Same
# app code as before (auth.py + guardrails.py don't care whether they're
# running on a VM or Cloud Run), just a much smaller run, pointed at your
# live Cloud Run URL instead of a VM.
#
# Run from Cloud Shell (same tab you used to deploy):
#   API_KEY=<your key> locust -f locustfile.py --headless -u 20 -r 5 -t 20s \
#     --host=https://<your-cloud-run-url> --csv=load_test
# Then read the 95%ile column off the /chat row in load_test_stats.csv --
# that's your P95. One clean run is enough; you don't need a bigger one.

import os

from locust import HttpUser, task, between

API_KEY = os.environ.get("API_KEY", "change-me-api-key")
DEMO_USERNAME = os.environ.get("DEMO_USERNAME", "demo")
DEMO_PASSWORD = os.environ.get("DEMO_PASSWORD", "demo123")


class ChatUser(HttpUser):
    wait_time = between(1, 3)

    def on_start(self):
        """Log in once per simulated user, cache the token + both required
        headers for every request after (Cloud Run's api-gateway route is
        JWT + API-key protected, same as it was on the VM)."""
        resp = self.client.post(
            "/auth/login", json={"username": DEMO_USERNAME, "password": DEMO_PASSWORD}
        )
        token = resp.json().get("access_token", "")
        self.client.headers.update(
            {"X-API-Key": API_KEY, "Authorization": f"Bearer {token}"}
        )

    @task
    def ask_chat(self):
        self.client.post("/chat", json={"message": "how many products do we have?"})
