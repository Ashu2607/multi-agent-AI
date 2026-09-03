# Production Readiness Checklist — Milestone 6

Checked off honestly as of this pass (2026-08-13). Unchecked items are
real gaps, not oversights — see the "why" column and `README.md` /
`DEPLOY.md` for what's needed to close each one.

| Done | Item | Evidence | Why (if unchecked) |
|---|---|---|---|
| ✅ | Docker Compose brings up the full stack with one command | `docker-compose.yml` (4 services: backend, ui, vectorstore, redis), `DEPLOY.md` §1 | — |
| ✅ | FastAPI backend deployable and verifiable on Cloud Run via curl | `Dockerfile`, `DEPLOY.md` §2 (exact `gcloud run deploy --source .` command + curl checks) | Dockerfile build-tested locally; actual `gcloud` run happens on the GCP VM, not this dev machine |
| ✅ | Both API-key and JWT required on protected endpoints | `app/auth.py`, `app/api.py` (`Depends(require_api_key)` app-wide + `Depends(require_jwt)` on every `/research*`/`/approvals*` route) | — |
| ✅ | Prompt-injection guardrail active and tested | `app/guardrails/` (ported + hardened from M4), wired into `/research` and `/research/stream` in `app/api.py`, regression-tested against a 20-row dataset in `tests/test_guardrails.py` | Tested against the dataset ported from M4; the trainer's shared 50-prompt `redteam_prompts.csv` is now also in this repo (see below) for the wider red-team pass |
| ❌ | 500-user Locust run completed against the VM Compose stack, real P95 recorded | `scripts/locustfile.py` (wired to this app's own `/auth/login` + `/research`, JWT+API-key) | Runner is in this repo and ready; needs to actually be executed live from the VM's SSH session (not reproducible from this dev machine) — `reports/load_test_stats.csv` not yet generated |
| ❌ | AIF360 bias audit run and interpreted | `scripts/bias_audit.py` + `data/bias_audit/loan_approval_data.csv` (trainer's shared dataset, copied verbatim from `ms6_cloudrun_demo/`) | Script is in this repo and ready (`python scripts/bias_audit.py`); not yet executed here, so `reports/bias_audit_results.json` and the written interpretation don't exist yet |
| ❌ | Model Card complete | — | Depends on the Locust P95 and red-team count above (Model Card Sections 4/5 need real numbers, not placeholders) |
| ❌ | NIST AI RMF worksheet complete | — | Same dependency — Measure/Manage sections need Step 4/6 evidence first |
| ❌ | Red-team results saved with a safe/concerning verdict | `scripts/redteam_runner.py` + `scripts/redteam_prompts.csv` (trainer's shared 50 prompts, copied verbatim from `ms6_cloudrun_demo/`) | Runner is in this repo and ready (`python scripts/redteam_runner.py --host ...`); not yet executed against a live deployment, so `reports/redteam_results.json` and the written safe/concerning verdict don't exist yet |

## What "done" actually means for the checked items

- **Compose**: `docker compose up -d --build` on the VM starts `backend`
  (FastAPI), `ui` (Streamlit), `vectorstore` (Chroma server), and `redis`
  on one Docker network, addressed by service name (`http://backend:8000`,
  `http://vectorstore:8000`, `redis://redis:6379`) — never localhost or a
  hardcoded IP.
- **Cloud Run**: same `Dockerfile` Compose's `backend` service uses;
  `gcloud run deploy --source .` triggers a Cloud Build of it. Verification
  is `curl` from inside the VM's own SSH session against `/health`,
  `/docs`, and three real `/research` queries — never a laptop browser
  (blocked by the sandbox's firewall).
- **JWT + API key**: `tests/test_api_security.py::test_business_route_rejects_api_key_without_jwt`
  is the direct regression test for the exact failure mode the build
  guide warns about — a route that accepts the API key alone with no
  token check actually wired in.
- **Guardrails**: `tests/test_guardrails.py` runs the ported M4 dataset
  (prompt injection, jailbreak, PII, toxicity, plus 4 new M6-hardening
  rows) through `app.guardrails.check_prompt` and asserts the exact
  expected action per row; `tests/test_api_security.py::test_research_blocks_prompt_injection_before_reaching_pipeline`
  proves the guardrail is actually reachable from the live `/research`
  endpoint, not just unit-tested in isolation.

## Sign-off status

**Not ready for a full Responsible-AI-board sign-off yet** — the
governance paperwork (bias audit, Model Card, NIST worksheet, shared
red-team run) is the explicit gap above. The deployment and security
hardening this pass covered (Compose, Cloud Run, required JWT+API-key,
guardrails) are done and evidenced. The trainer's shared M6 files
(`redteam_prompts.csv`, `loan_approval_data.csv`) are now in this repo
(`scripts/`, `data/bias_audit/`) along with runnable scripts adapted to
this app's actual endpoints (`scripts/redteam_runner.py`,
`scripts/locustfile.py`, `scripts/bias_audit.py`) — `model_card_template.md`
and `nist_ai_rmf_worksheet.md` still need to be pulled in. Next step:
actually run Steps 4-6 against the live VM Compose stack and fill in the
Model Card / NIST worksheet with the real output.
