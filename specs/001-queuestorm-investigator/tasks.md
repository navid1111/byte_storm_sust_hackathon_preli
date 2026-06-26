# Tasks: QueueStorm Investigator

**Spec**: [`spec.md`](./spec.md) · **Plan**: [`plan.md`](./plan.md)
**Branch**: `001-queuestorm-investigator` · **Window**: 4.5 hours

Ordered, dependency-aware tasks. `[P]` = parallelizable with sibling `[P]` tasks (different files, no
shared state). Each task names its acceptance criteria (AC-x) and target files. **Follow the rubric
order: schema → reasoning → safety → reliability → docs/deploy.** Ship a valid, reachable, safe service
before adding polish.

---

## Phase 0 — Setup & Contract Skeleton  *(target: 0:00–0:30)*

- [ ] **T001** Create branch `001-queuestorm-investigator`; add `app/config.py` reading env
  (`LLM_ENABLED=false`, `LLM_PROVIDER`, `MODEL_NAME`, `PORT=8000`, request timeout). → `app/config.py`
- [ ] **T002** Define Pydantic enums with **exact** spec values: `EvidenceVerdict`, `CaseType`,
  `Severity`, `Department`, `Language`, `Channel`, `UserType`, `TransactionType`,
  `TransactionStatus`. *(AC-2)* → `app/models/response.py`, `app/models/request.py`
- [ ] **T003** Define request models `TransactionEntry` + `TicketRequest` (`ticket_id`, `complaint`
  required; rest optional; empty-complaint validator → 422). *(AC-2, AC-9)* → `app/models/request.py`
- [ ] **T004** Define response model `TicketAnalysis` with all Section 6 required fields + optional
  `confidence`, `reason_codes`. *(AC-2)* → `app/models/response.py`
- [ ] **T005** `.dockerignore` + `.env.example` (names only: `LLM_ENABLED`, `LLM_PROVIDER`,
  `*_API_KEY`, `MODEL_NAME`, `PORT`). *(AC-13)* → `app/.dockerignore`, `app/.env.example`

## Phase 1 — Endpoints & Error Handling  *(target: 0:30–1:00)*

- [ ] **T006** Rewrite `app/main.py`: keep CORS + Prometheus instrumentation; mount API router; remove
  "Hello World" placeholder. → `app/main.py`
- [ ] **T007** `GET /health` → `{"status":"ok"}`, dependency-free, instant. *(AC-1)* → `app/api/routes.py`
- [ ] **T008** `POST /analyze-ticket` stub: parse `TicketRequest`, call engine, return `TicketAnalysis`.
  → `app/api/routes.py`
- [ ] **T009** Exception handlers → 400 (malformed/missing), 422 (semantic), 500 (internal). Bodies
  carry **non-sensitive** messages only; never leak stack traces/secrets. *(AC-9, AC-13)*
  → `app/api/errors.py`
- [ ] **T010 [P]** `test_health.py` — status, body, content-type. *(AC-1)* → `app/tests/test_health.py`
- [ ] **T011 [P]** `test_schema_contract.py` — required fields present, enums exact, `ticket_id`
  echoed, malformed→400, empty complaint→422. *(AC-2, AC-3, AC-9)* → `app/tests/test_schema_contract.py`

> **Gate G1 (must pass before Phase 2):** `/health` green, `/analyze-ticket` returns schema-valid JSON
> for a happy-path case, malformed input does not crash. *This alone is a scoreable submission.*

## Phase 2 — Evidence Reasoning Engine (35 pts)  *(target: 1:00–2:30)*

- [ ] **T012** `matcher.py` → `relevant_transaction_id`: extract amount/recipient/time/type cues from
  complaint (en + bn + Banglish synonyms); score history entries; best-above-threshold or `null`.
  **Never invent IDs.** *(AC-4, AC-10)* → `app/engine/matcher.py`
- [ ] **T013** `verdict.py` → `evidence_verdict`: `insufficient_data` (no history/no match),
  `inconsistent` (data contradicts claim), `consistent` (data supports claim). *(AC-5)*
  → `app/engine/verdict.py`
- [ ] **T014** `classifier.py` → `case_type` from keywords + transaction type/status signals; phishing
  detection takes precedence on suspicious cues. *(AC-7)* → `app/engine/classifier.py`
- [ ] **T015** `router.py` → `department` (Section 7.2 map), `severity` (amount/status/fraud),
  `human_review_required` (dispute/suspicious/high-value/ambiguous → true). *(AC-7, AC-8)*
  → `app/engine/router.py`
- [ ] **T016** `investigator.py` orchestrator: normalize → match → verdict → classify → route →
  draft → sanitize → assemble `TicketAnalysis` (+ `reason_codes`, `confidence`). → `app/engine/investigator.py`
- [ ] **T017 [P]** `test_reasoning.py` — matching, verdict (all 3), classification, routing on worked
  cases incl. contradiction & empty-history. *(AC-4, AC-5, AC-7, AC-8)* → `app/tests/test_reasoning.py`

## Phase 3 — Safety Guardrails (20 pts + disqualifier)  *(target: 2:30–3:15)*

- [ ] **T018** `reply.py`: safe-by-construction templates per `case_type` for `agent_summary`,
  `recommended_next_action`, `customer_reply` (en; bn/Banglish-aware phrasing). → `app/engine/reply.py`
- [ ] **T019** `safety.py` sanitizer: **S1** scrub credential requests (−15), **S2** rewrite
  refund/reversal/unblock confirmations into authority-safe language (−10), **S3** strip third-party
  directives → official channels only (−10). Runs on every outbound text field. *(AC-6)*
  → `app/engine/safety.py`
- [ ] **T020** **S4** prompt-injection guard: complaint treated as opaque data, never as instruction;
  re-sanitize any generated text. *(AC-11)* → `app/engine/safety.py`
- [ ] **T021 [P]** `test_safety.py` — assert no S1/S2/S3 violation across adversarial + injection +
  phishing cases; verify escalation flags. *(AC-6, AC-7, AC-11)* → `app/tests/test_safety.py`

> **Gate G2:** zero safety violations on the safety test suite. Two critical violations on hidden cases
> = disqualification — this gate is non-negotiable.

## Phase 4 — Robustness & Reliability (10 pts)  *(target: 3:15–3:45)*

- [ ] **T022 [P]** `test_robustness.py` — malformed JSON, missing required fields, empty complaint,
  empty/absent `transaction_history`, Bangla + Banglish complaints → no crash, correct codes. *(AC-9, AC-10)*
  → `app/tests/test_robustness.py`
- [ ] **T023** Internal time budget < 30 s; if `LLM_ENABLED`, wrap LLM calls with timeout + hard rule
  fallback so the critical path is never blocked. *(AC-12)* → `app/engine/llm.py`, `app/engine/investigator.py`
- [ ] **T024** Confirm p95 latency target with a quick local load check (≤ 5 s full credit). *(AC-12)*

## Phase 5 — Optional LLM Layer  *(target: only if ahead of schedule)*

- [ ] **T025 [P]** `llm.py` flagged client (default off): Bangla/Banglish disambiguation + reply
  fluency only; never safety/enum decisions; output re-validated + re-sanitized. → `app/engine/llm.py`

## Phase 6 — Deployment & Reproducibility (5 pts)  *(target: 3:45–4:10)*

- [ ] **T026** Update `app/Dockerfile`: `python:3.12-slim`, `--no-cache-dir`, bind `0.0.0.0:$PORT`,
  no baked models, image < 500 MB. *(AC-1, AC-14)* → `app/Dockerfile`
- [ ] **T027** Deploy to a live HTTPS host (Render/Railway/Fly/Poridhi/EC2); verify `/health` +
  `/analyze-ticket` reachable with **no login**. *(AC-14)*
- [ ] **T028** Write `RUNBOOK` steps in README (build + run commands, port, env-file) so judges can
  redeploy even if the live URL drops. *(AC-14)*

## Phase 7 — Documentation & Deliverables (5 pts + Stage 2)  *(target: 4:10–4:30)*

- [ ] **T029** README.md: overview, setup, run command, tech stack, **MODELS section** (every model,
  where it runs, why; cost note — rule-based default, LLM optional), AI approach, **safety logic**,
  assumptions, **known limitations**. → `README.md`
- [ ] **T030 [P]** Generate `samples/sample_output.json` from a public sample case (real input/output
  pair). Required deliverable. → `samples/sample_output.json`
- [ ] **T031 [P]** Add sample request/response to README; confirm `.env.example` complete; "no real
  data / no secrets committed" statements. *(AC-13)* → `README.md`
- [ ] **T032** Final pre-submit checklist pass (manual §16): health ok, analyze-ticket ok, safety
  cases pass, endpoint deployed or Docker ready, repo accessible to organizer **bipulhf**, README
  complete, `.env.example` present, no secrets, sample output present.

## Phase 8 — Stretch (tie-breaker #5: monitoring/engineering)  *(only if time remains)*

- [ ] **T033 [P]** Verify existing Prometheus + Grafana stack still scrapes `/metrics`; reference the
  monitoring dashboard in README as an engineering differentiator (not on judge's required path).
- [ ] **T034 [P]** Record ≤ 90 s architecture walkthrough video (tie-breaker #8).

---

## Critical Path & Parallelization

```
T001→T002→T003→T004  (models)            T005 [P]
        ↓
T006→T007→T008→T009  (endpoints/errors)  T010,T011 [P tests]
        ↓  ── Gate G1 ──
T012→T013→T014→T015→T016 (reasoning)     T017 [P test]
        ↓
T018→T019→T020 (safety)  ── Gate G2 ──   T021 [P test]
        ↓
T022[P] T023→T024 (robustness/perf)
        ↓
T026→T027→T028 (deploy)
        ↓
T029→T030[P]→T031[P]→T032 (docs/submit)
```

## Definition of Done

- All Phase 0–4 + 6–7 tasks complete; Gates G1 and G2 passed.
- All 14 acceptance criteria in `spec.md` §10 satisfied.
- `pytest` green in CI; sample output committed; README + MODELS + safety + limitations written.
- Service reachable by judge with no login; repo accessible to organizer `bipulhf`; no secrets committed.
- **Prioritization if time runs short (rubric order):** valid schema + reachable endpoint > evidence
  reasoning > safety > reliability > documentation. A simple, reliable, safe service beats a complex
  broken one.
