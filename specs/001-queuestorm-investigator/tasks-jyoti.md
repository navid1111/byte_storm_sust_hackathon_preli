# Tasks: QueueStorm Investigator (Jyoti's Tasks)

**Spec**: [`spec.md`](./spec.md) · **Plan**: [`plan.md`](./plan.md) · **Decision rules**: [`decision-rules.md`](./decision-rules.md)
**Branch**: `001-queuestorm-investigator` · **Window**: 4.5 hours

Ordered, dependency-aware tasks. `[P]` = parallelizable with sibling `[P]` tasks (different files, no
shared state). Each task names its **owner**, its acceptance criteria (AC-x), and target files.
**Follow the rubric order: schema → reasoning → safety → reliability → docs/deploy.** Ship a valid,
reachable, safe service before adding polish.

### Owners

| Owner | Focus | Load |
|-------|-------|------|
| **Jyoti** | Fixtures + tests + documentation (test suites, README, sample output, video) | 8 tasks |

---

## Phase 0 — Setup & Contract Skeleton  *(target: 0:00–0:30)*

- [x] **T000 [P0]** _(Jyoti)_ Hand-author ~10 fixture cases (request + expected `relevant_transaction_id`,
  `evidence_verdict`, `case_type`, `department`, severity, safe-reply intent) from the spec examples +
  [`decision-rules.md`](./decision-rules.md). **Blocks T017.** Cover: wrong_transfer/consistent,
  payment_failed/inconsistent, empty-history/insufficient_data, phishing, duplicate, Bangla, Banglish,
  prompt-injection. Swap for real `SUST_Preli_Sample_Cases.json` when obtained. → `app/tests/fixtures/cases.json`

## Phase 1 — Endpoints & Error Handling  *(target: 0:00–0:30)*

- [x] **T010 [P]** _(Jyoti)_ `test_health.py` — status, body, content-type. *(AC-1)* → `app/tests/test_health.py`

> **Gate G1 (must pass before Phase 2):** `/health` green, `/analyze-ticket` returns schema-valid JSON
> for a happy-path case, malformed input does not crash. *This alone is a scoreable submission.*

## Phase 2 — Evidence Reasoning Engine (35 pts)  *(target: 0:30–1:30)*

> Implement against [`decision-rules.md`](./decision-rules.md) — cue weights (§1), verdict logic (§2),
> case/department/severity/review tables (§3), synonyms (§4), phishing cues (§5). Code and tests both
> read those exact boundaries; do not invent ad-hoc thresholds.

- [x] **T017 [P]** _(Jyoti)_ `test_reasoning.py` — matching, verdict (all 3), classification, routing on worked
  cases incl. contradiction & empty-history. *(AC-4, AC-5, AC-7, AC-8)* → `app/tests/test_reasoning.py`

## Phase 3 — Safety Guardrails (20 pts + disqualifier)  *(target: 1:30–2:15)*

- [x] **T021 [P]** _(Jyoti)_ `test_safety.py` — assert no S1/S2/S3 violation across adversarial + injection +
  phishing cases; verify escalation flags. *(AC-6, AC-7, AC-11)* → `app/tests/test_safety.py`

> **Gate G2:** zero safety violations on the safety test suite. Two critical violations on hidden cases
> = disqualification — this gate is non-negotiable.

## Phase 4 — Robustness & Reliability (10 pts)  *(target: 2:15–2:45)*

- [x] **T022 [P]** _(Jyoti)_ `test_robustness.py` — malformed JSON, missing required fields, empty complaint,
  empty/absent `transaction_history`, Bangla + Banglish complaints → no crash, correct codes. *(AC-9, AC-10)*
  → `app/tests/test_robustness.py`

## Phase 7 — Documentation & Deliverables (5 pts + Stage 2)  *(target: 2:45–3:00)*

- [x] **T029** _(Jyoti)_ README.md: overview, setup, run command, tech stack, **MODELS section** (every model,
  where it runs, why; cost note — rule-based default, LLM optional), AI approach, **safety logic**,
  assumptions, **known limitations**. → `README.md`
- [x] **T031 [P]** _(Jyoti)_ Add sample request/response to README; confirm `.env.example` complete; "no real
  data / no secrets committed" statements. *(AC-13)* → `README.md`

## Phase 8 — Stretch (tie-breaker #5: monitoring/engineering)  *(only if time remains)*

- [ ] **T034 [P]** _(Jyoti)_ Record ≤ 90 s architecture walkthrough video (tie-breaker #8).

---

## Critical Path & Parallelization (Jyoti's perspective)

```
T000 [P0 fixtures] ──────────────┐ (blocks T017)
                                 ↓
                               T010 [P test]
                                 ↓  ── Gate G1 ──
                               T017 [P test ← needs T000]
                                 ↓
                               T021 [P test]  ── Gate G2 ──
                                 ↓
                               T022 [P test]
                                 ↓
                               T029 & T031 (docs)
                                 ↓
                               T034 (video)
```

## Definition of Done

- All Jyoti's tasks complete; Gates G1 and G2 passed.
- Corresponding acceptance criteria satisfied.
