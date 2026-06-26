# Pre-submit checklist — QueueStorm Investigator

> Last full pass: **2026-06-26** by Navid. Each item is verifiable from this repo
> with a one-line command. If any line fails, **fix the underlying issue first**,
> then re-run; don't just untick the box.

## 1. Schema & contract (rubric: 15 pts)

- [x] **T002–T004**: enums + `TicketRequest` + `TicketAnalysis` defined with spec-exact
      values. → `app/models/`
- [x] **AC-2**: enums are exactly the spec values (no alias drift). →
      `app/tests/test_schema_contract.py` (enforced)
- [x] **AC-9**: malformed JSON / empty complaint / missing fields return 400 / 422, not 500. →
      `app/tests/test_schema_contract.py`, `app/tests/test_robustness.py`

## 2. Evidence reasoning (rubric: 35 pts)

- [x] **T012–T014**: `matcher.py` / `verdict.py` / `classifier.py` match decision-rules §1–§4. →
      `app/engine/`
- [x] **T015**: `router.py` covers department/severity/human_review per §3.2–§3.4. →
      `app/engine/router.py`
- [x] **T016**: `investigator.py` orchestrates normalize → match → verdict → classify →
      route → draft → sanitize → assemble. → `app/engine/investigator.py`
- [x] **AC-4**: an ID is **never invented** when nothing matches — `null` is returned. →
      `app/tests/test_reasoning.py`

## 3. Safety guardrails (rubric: 20 pts + disqualifier)

- [x] **T018**: `reply.py` safe-by-construction templates per case type. →
      `app/engine/reply.py`
- [x] **T019**: `safety.py` S1/S2/S3 sanitizer runs on every outbound text field. →
      `app/engine/safety.py`
- [x] **T020**: **S4** prompt-injection guard — complaint is data, not instruction;
      LLM output is re-sanitized. → `app/engine/safety.py`
- [x] **Gate G2**: zero S1/S2/S3 violations on the safety suite.
      Verify: `cd app && pytest tests/test_safety.py` → all green.

## 4. Reliability & latency (rubric: 10 pts)

- [x] **T023**: Internal time budget < 30 s; LLM gated with timeout + rule fallback.
      → `app/engine/llm.py`, `app/engine/investigator.py`
- [x] **T024 — local latency**: `bash scripts/latency_check.sh http://localhost:8000`
      → expects `PASS p95 < 5000ms`.
      **Measured 2026-06-26:** p95 = **27 ms** local / **339 ms** live Render.
- [x] **AC-12**: p95 ≤ 5 s full credit. **Achieved with ~15× margin.**

## 5. Endpoints & health

- [x] **T007**: `GET /health` → `{"status":"ok"}`. Verify: `curl /health`
- [x] **T008**: `POST /analyze-ticket` stub wired to investigator. Verify:
      `curl -X POST /analyze-ticket -H 'content-type: application/json' --data @samples/sample_input.json`
- [x] **T006**: `main.py` retains CORS + Prometheus instrumentation; no "Hello World"
      placeholder. → `app/main.py`

## 6. Deployment & reproducibility (rubric: 5 pts)

- [x] **T026**: `app/Dockerfile` uses `python:3.12-slim`, `--no-cache-dir`, binds
      `0.0.0.0:$PORT`, no baked models, target image < 500 MB.
- [x] **T027 — live HTTPS reachable**: deployed at
      `https://byte-storm-sust-hackathon-preli.onrender.com`. **Verified 2026-06-26** —
      `/health`, `/analyze-ticket`, `/metrics` all respond; no login required.
- [x] **T028**: README has build + run + env-file steps so judges can redeploy if the
      live URL drops.

## 7. Documentation & deliverables

- [x] **T029**: README has overview, setup, run, tech stack, **MODELS section**,
      AI approach, **safety logic**, assumptions, **known limitations**. → `README.md`
- [x] **T030 — sample output**: `samples/sample_output.json` committed and matches a
      live run against `samples/sample_input.json` (814-byte response, identical
      bytes when re-run against the local docker stack).
- [x] **T031**: README has a sample request/response section; `.env.example` complete
      (variable names only); "no real data / no secrets committed" statements present.

## 8. Tests & CI

- [x] **T010, T011, T017, T021, T022**: full test suite present. Verify:
      `cd app && pytest` → expect **260 passed**, coverage ≥ 85 %.
      **Measured 2026-06-26:** **260 passed, 97.91 % coverage.**
- [x] **CI green**: `.github/workflows/ci.yml` runs `pytest` on push/PR to `main`.

## 9. Monitoring / engineering differentiator (tie-breaker #5)

- [x] **T033 — Prometheus + Grafana**: `docker-compose up -d` brings up the full stack;
      Prometheus `app` target is `up`; Grafana **FastAPI Dashboard** is auto-provisioned.
      **Verified 2026-06-26** via `curl http://localhost:9090/api/v1/targets` and
      Grafana `/api/search?query=fast`.
      README has a "Monitoring" section pointing to both UIs.

## 10. Hygiene & secrets

- [x] **T005**: `app/.dockerignore` excludes `.env`; `app/.env.example` is names-only.
- [x] **AC-13**: root `.gitignore` excludes `.env`; error responses never leak stack
      traces, file paths, env-var names, or model internals. → `app/api/errors.py`
- [x] **No secrets in repo**: `git grep -nE '(api[_-]?key|secret|token|password)' -- ':!.git'`
      should show only `.env.example` placeholders and prose mentions.

## 11. Pre-submit verification one-liner

Run from repo root (assumes `docker-compose up -d` already running):

```bash
cd app && pytest                                          # 260 passed
cd .. && bash scripts/smoke_test.sh                       # 10/10 PASS
bash scripts/latency_check.sh http://localhost:8000       # p95 < 5000 ms
bash scripts/smoke_test.sh https://byte-storm-sust-hackathon-preli.onrender.com  # 10/10 PASS (with -m 60)
bash scripts/latency_check.sh https://byte-storm-sust-hackathon-preli.onrender.com  # p95 < 5000 ms
```

All five should exit 0 and emit the expected `PASS` lines. If any fails, **fix the
underlying issue before submitting**.

## Rubric priority reminder

If time runs short, the rubric order is:

> **schema → reasoning → safety → reliability → docs/deploy**

A simple, reliable, safe service beats a complex broken one. Never trade a
**schema-valid, safe, reachable** service for an extra feature.

---

## Sign-off

- [x] **T032** — Final pre-submit checklist pass complete (Navid, 2026-06-26).
- [x] All `tasks.md` checkboxes ticked to reflect actual state.
- [x] Repo accessible to organizer `bipulhf` on GitHub.