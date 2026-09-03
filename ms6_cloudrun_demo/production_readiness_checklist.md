# Production Readiness Checklist — AI Platform (M6 demo)

Fill this in honestly after you actually run each step — an unchecked box
with a one-line reason ("skipped, ran out of time after Wednesday's
Qdrant intro") is worth more than a checked box that isn't true. See the
Evaluation Criteria doc: disclosed gaps are scored fairly, hidden ones
are not.

- [ ] Docker Compose brings up the full stack (postgres, memory-service,
      chat-service, sql-service, api-gateway, ui) with one command
- [ ] FastAPI backend (api-gateway) deployed and verified reachable on
      Cloud Run (via curl from inside the VM/Cloud Shell, not a laptop browser)
- [ ] Both API-key and JWT required on protected endpoints (/chat, /sql,
      /memory/{id}) — confirmed a request WITHOUT either one correctly
      fails with 401
- [ ] Prompt-injection guardrail active, tested against the red-team set
      (real block count recorded, not assumed)
- [ ] 500-user Locust run completed against the VM Compose stack, real
      P95 recorded (not Cloud Run, not a guessed number)
- [ ] AIF360 bias audit run and interpreted (not just printed)
- [ ] Model Card complete, using real numbers from the steps above
- [ ] NIST AI RMF worksheet complete, own answers beyond the given example
- [ ] Red-team results saved with a safe/concerning verdict you wrote
      yourself after reading the results
- [ ] .env (real secrets) is NOT in the zip — only .env.example is
- [ ] Redeploy from scratch works using only the README's exact commands
      (this is what Friday morning actually tests)
