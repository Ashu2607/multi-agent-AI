"""Red-team runner (M6 Step 4 / Category 8 evidence).

Runs the 50 shared adversarial prompts (`scripts/redteam_prompts.csv`,
copied verbatim from the trainer's `ms6_cloudrun_demo/redteam_prompts.csv`
so every student's cohort is red-teaming the same set) against THIS repo's
own deployed system - `POST /auth/login` then `POST /research` - not the
separate GCP-deploy demo app's `/chat` toy endpoint.

Run from wherever the deployed backend is reachable (VM SSH session /
Cloud Shell - see DEPLOY.md; a corporate-network laptop browser can't
reach it, but this is a plain HTTP client so curl-equivalent access is
enough):

    API_KEY=... DEMO_USERNAME=demo DEMO_PASSWORD=... \\
      python scripts/redteam_runner.py --host http://localhost:8000

What it does:
  1. Logs in once (POST /auth/login) to get a JWT, same as a real client.
  2. POSTs each of the 50 prompts to POST /research as {"task": prompt}.
  3. A prompt this app's guardrail pipeline blocks comes back as an actual
     HTTP 400 (`app/api.py::_guard`) - that IS the real verdict, read off
     the live response, not guessed or hand-scored.
  4. Saves every prompt + outcome to reports/redteam_results.json.
  5. Prints a blocked/total count by category - the categories this
     guardrail is actually scoped to catch (prompt_injection, jailbreak)
     are expected to score high; the others (PII/Data Extraction, Harmful
     Content, Scope Abuse) are NOT this guardrail's job, so a prompt
     getting through them is not automatically "concerning" - see the
     printed reminder below.

"Concerning" is a judgment call this script does not make for you: a
prompt that isn't blocked but whose reply still refuses/deflects is a
safe outcome, just not one this script counts. Read every NOT-blocked
row in redteam_results.json yourself before writing the Category 8 /
Model Card verdict.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path

import httpx

ROOT_DIR = Path(__file__).resolve().parent.parent

DEMO_USERNAME = os.environ.get("DEMO_USERNAME", "demo")
DEMO_PASSWORD = os.environ.get("DEMO_PASSWORD", "")
API_KEY = os.environ.get("API_KEY", "")  # reads from the same shell env as
# the deployed backend's own .env - no manual editing needed. An empty
# value will correctly 401 every request rather than silently pass.


def _extract_reply(data: dict) -> str:
    """Best-effort human-readable summary of a /research 200 response.
    The endpoint returns the full LangGraph state, not a single `reply`
    field, so pull the most meaningful text out of it: the Writer's
    executive summary if a draft was produced, else the latest finding
    summary, else a note that the pipeline stopped without a draft."""
    draft = data.get("draft")
    if draft and draft.get("executive_summary"):
        return draft["executive_summary"]
    findings = data.get("findings") or []
    if findings:
        return findings[-1].get("summary", "")
    return "(pipeline ran but produced no draft or findings - see full JSON)"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="http://localhost:8000")
    parser.add_argument("--prompts", default=str(ROOT_DIR / "scripts" / "redteam_prompts.csv"))
    parser.add_argument("--out", default=str(ROOT_DIR / "reports" / "redteam_results.json"))
    args = parser.parse_args()

    if not API_KEY:
        print("WARNING: API_KEY is not set in this shell - every request will "
              "401 before it ever reaches the guardrail, which will look like "
              "'0 blocked' for every category. Export API_KEY first.", file=sys.stderr)

    with httpx.Client(base_url=args.host, timeout=60) as client:
        login = client.post(
            "/auth/login",
            json={"username": DEMO_USERNAME, "password": DEMO_PASSWORD},
            headers={"X-API-Key": API_KEY},
        )
        login.raise_for_status()
        token = login.json()["access_token"]
        headers = {"X-API-Key": API_KEY, "Authorization": f"Bearer {token}"}

        with open(args.prompts, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))

        results = []
        blocked_count = 0
        for row in rows:
            prompt = row["prompt"]
            try:
                resp = client.post("/research", json={"task": prompt}, headers=headers)
            except httpx.HTTPError as exc:
                results.append(
                    {"id": row["id"], "category": row["category"], "prompt": prompt,
                     "blocked_by_guardrail": False, "status_code": None,
                     "reply": f"(request error: {exc})"}
                )
                continue

            if resp.status_code == 400:
                blocked = True
                reply = resp.json().get("detail", "")
            elif resp.status_code == 200:
                blocked = False
                reply = _extract_reply(resp.json())
            else:
                blocked = False
                reply = f"(unexpected status {resp.status_code}: {resp.text[:300]})"

            if blocked:
                blocked_count += 1
            results.append(
                {
                    "id": row["id"],
                    "category": row["category"],
                    "prompt": prompt,
                    "blocked_by_guardrail": blocked,
                    "status_code": resp.status_code,
                    "reply": reply,
                }
            )
            print(f"  [{row['id']:>2}/{len(rows)}] {row['category']:<20} "
                  f"{'BLOCKED' if blocked else 'passed':<8}")

        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)

        print(f"\nRan {len(results)} prompts against {args.host}")
        print(f"Blocked by guardrail: {blocked_count}/{len(results)}")
        print("\nBy category:")
        by_cat: dict[str, list[int]] = {}
        for r in results:
            by_cat.setdefault(r["category"], [0, 0])
            by_cat[r["category"]][1] += 1
            if r["blocked_by_guardrail"]:
                by_cat[r["category"]][0] += 1
        for cat, (blocked, total) in by_cat.items():
            print(f"  {cat}: {blocked}/{total} blocked")
        print(f"\nSaved to {out_path.relative_to(ROOT_DIR)} - now read the "
              "NOT-blocked rows yourself and write your own safe-vs-concerning "
              "verdict (Category 8 needs a real example of each, not just this count).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
