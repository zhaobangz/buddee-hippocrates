# Buddi Eval Harness

**Owner:** founder + part-time clinical advisor (Hire #1, manual §5.2)
**Manual reference:** §2.2 week 3 deliverable, §7.2 Risk #2 mitigation

This is the offline regression harness that turns the agent's
hallucination risk from "we hope it's fine" into a measurable,
PR-gated metric. Every code change to `core/agent.py`,
`core/llm_manager.py`, or `core/rag_engine.py` should be run through
`run_eval.py` before merge.

## Layout

```
evals/
├── README.md                ← this file
├── golden/                  ← curated, clinician-labeled cases
│   ├── case_001.json
│   ├── case_002.json
│   └── ...
├── synthea/                 ← synthetic FHIR bundles (manual §2.2 week 4)
│   └── bundle_*.json
├── run_eval.py              ← the CI entry point
└── metrics.py               ← precision / recall / abstain-rate math
```

A **golden case** is a single JSON document with the shape:

```json
{
    "case_id": "case_007",
    "clinician_id": "advisor:dr-chen",
    "labeled_at": "2026-05-20T12:00:00Z",
    "specialty": "primary_care",
    "tenant_id_hint": "synthetic",
    "note": "67yo male with type 2 diabetes, eGFR 51, urine ACR 42 mg/g ...",
    "billed_codes": ["E11.9", "I10"],
    "expected_codes": ["E11.22", "N18.31", "I12.9"],
    "must_abstain_codes": [],
    "notes": "Diabetic CKD case used to anchor the floor at 0.70."
}
```

Two label sets matter:

* `expected_codes` — the codes a careful clinician would surface.
  Counted in precision / recall.
* `must_abstain_codes` — codes the agent must NOT surface (i.e. they
  are out of scope for this encounter). A non-empty intersection
  between `must_abstain_codes` and the agent's surfaced output is a
  hard fail.

## Running locally

```bash
# Real LLM call (requires ANTHROPIC_API_KEY + BUDDI_BAA_CONFIRMED=1
# because the golden cases include realistic-sized notes):
python -m evals.run_eval --cases evals/golden --output /tmp/eval.json

# Deterministic offline mode (no LLM call; exercises the harness
# against the agent's demo fallback):
python -m evals.run_eval --cases evals/golden --offline
```

## CI gate

`.github/workflows/main.yml` runs `python -m evals.run_eval --offline`
on every PR. The job fails when:

* Top-3-codes precision drops by more than 5% versus the baseline in
  `evals/baseline.json`, or
* Recall drops by more than 5%, or
* Any `must_abstain_codes` violation is detected.

The baseline file is human-edited — bump it intentionally after a
clinician review confirms the new behaviour is desired.

## Growing the golden set

The seed set is ten cases (one per major HCC bucket the manual's
primary ICP cares about — diabetes complications, CHF, COPD, CKD).
Hire #1's first deliverable (§5.2) is to grow this to 100, with two
constraints:

1. No real PHI. Cases must be synthetic or de-identified to HIPAA
   Safe Harbor § 164.514(b)(2).
2. Every case must be reviewed by a board-certified clinician and
   carry their `clinician_id` so a downstream auditor can trace
   the label back to a human.
