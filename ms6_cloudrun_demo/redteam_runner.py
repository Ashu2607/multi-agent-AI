"""
redteam_runner.py -- runs the 50 shared adversarial prompts against the
demo app's own deployed /chat endpoint (M6 Step 4), the same file every
student adapts for their own capstone.

Run this from inside your VM's SSH session, Compose stack already up:
    python3 redteam_runner.py --host http://localhost:8000

What it does:
  1. Logs in once (POST /auth/login) to get a JWT, same as a real client.
  2. Posts each of the 50 prompts from redteam_prompts.csv to /chat.
  3. Reads `blocked_by_guardrail` off each response -- that field IS the
     guardrail's real verdict, not something this script has to judge.
  4. Saves every prompt + response to redteam_results.json.
  5. Prints a safe/concerning count by category -- read through the
     concerning ones yourself before writing your Model Card/NIST
     sections; this script does not replace that judgment call.

"Concerning" here means: NOT blocked by the guardrail AND not a case
where the underlying reply itself refused/deflected. This script flags
candidates for you to read -- it does not auto-decide safe vs concerning
on your behalf, per the M6 spec's "no scoring script needed" note.
"""
import argparse
import csv
import json
import os
import sys

import httpx

DEMO_USERNAME = os.environ.get("DEMO_USERNAME", "demo")
DEMO_PASSWORD = os.environ.get("DEMO_PASSWORD", "demo123")
API_KEY = os.environ.get("API_KEY", "change-me-api-key")  # reads from your
# shell env, same $API_KEY you already exported in Step 1 -- no manual
# editing needed. Only falls back to the placeholder (which will 401) if
# API_KEY genuinely isn't set in your shell.


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="http://localhost:8000")
    parser.add_argument("--prompts", default="redteam_prompts.csv")
    parser.add_argument("--out", default="redteam_results.json")
    args = parser.parse_args()

    with httpx.Client(base_url=args.host, timeout=30) as client:
        login = client.post("/auth/login", json={"username": DEMO_USERNAME, "password": DEMO_PASSWORD})
        login.raise_for_status()
        token = login.json()["access_token"]
        headers = {"X-API-Key": API_KEY, "Authorization": f"Bearer {token}"}

        with open(args.prompts, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))

        results = []
        blocked_count = 0
        for row in rows:
            try:
                resp = client.post("/chat", json={"message": row["prompt"]}, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                blocked = data.get("blocked_by_guardrail", False)
            except httpx.HTTPError as exc:
                data = {"error": str(exc)}
                blocked = False
            if blocked:
                blocked_count += 1
            results.append(
                {
                    "id": row["id"],
                    "category": row["category"],
                    "prompt": row["prompt"],
                    "blocked_by_guardrail": blocked,
                    "reply": data.get("reply", ""),
                }
            )

        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)

        print(f"Ran {len(results)} prompts against {args.host}")
        print(f"Blocked by guardrail: {blocked_count}/{len(results)}")
        print("\nBy category:")
        by_cat = {}
        for r in results:
            by_cat.setdefault(r["category"], [0, 0])
            by_cat[r["category"]][1] += 1
            if r["blocked_by_guardrail"]:
                by_cat[r["category"]][0] += 1
        for cat, (blocked, total) in by_cat.items():
            print(f"  {cat}: {blocked}/{total} blocked")
        print(f"\nSaved to {args.out} -- now read the NOT-blocked ones yourself and")
        print("write your own safe-vs-concerning verdict (see Build Guide Step 4).")


if __name__ == "__main__":
    sys.exit(main())
