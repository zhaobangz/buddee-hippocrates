"""CI / local entry point for the eval regression gate.

Usage:

    # CI / dev (no real LLM call, no PHI risk):
    python -m evals.run_eval --cases evals/golden --offline

    # Real-LLM run (requires ANTHROPIC_API_KEY + BUDDI_BAA_CONFIRMED=1):
    python -m evals.run_eval --cases evals/golden --output reports/eval.json

The `--offline` path runs the deterministic `_demo_shadow_result`
artifact from ``backend/api.py`` against each golden case. This is the
cheapest possible safety net — it cannot tell you whether the LLM is
hallucinating, but it does tell you whether a refactor of the safety
filter, the schemas, or the demo fallback broke the surfacing logic
for the seed set. The full eval (LLM-on) is run nightly via a
separate workflow once the BAA is in place.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List

# We intentionally import lazily inside ``main()`` so plain
# ``python -m evals.run_eval --help`` works without requiring
# the heavyweight ``backend.api`` import chain (FastAPI, SQLAlchemy,
# pgvector).

from evals.metrics import (
    CaseScore,
    aggregate,
    regression_against_baseline,
    score_case,
)

logger = logging.getLogger("evals.run_eval")


def _load_cases(cases_dir: Path) -> List[Dict[str, Any]]:
    """Load golden cases from a directory.

    When ``cases_dir`` is ``evals/golden`` (the default), the loader
    checks for an ``evals/golden/v1/`` subdirectory first — this is where
    ``scripts/ingest_golden_labels.py`` writes validated cases from the
    MD advisor's spreadsheet. If ``v1/`` exists and contains at least one
    ``case_*.json`` file it is used; otherwise the seed set in
    ``evals/golden/`` is the fallback.
    """
    # P‑B1: auto‑select v1/ when present.
    v1_dir = cases_dir / "v1"
    if cases_dir.name == "golden" and v1_dir.is_dir():
        v1_cases = sorted(v1_dir.glob("case_*.json"))
        if v1_cases:
            cases_dir = v1_dir

    cases: List[Dict[str, Any]] = []
    for path in sorted(cases_dir.glob("case_*.json")):
        try:
            cases.append(json.loads(path.read_text(encoding="utf-8")))
        except json.JSONDecodeError as e:
            raise SystemExit(f"Malformed golden case {path}: {e}") from e
    if not cases:
        raise SystemExit(f"No golden cases found under {cases_dir}")
    return cases


def _shadow_result_for_case(case: Dict[str, Any], *, offline: bool) -> Dict[str, Any]:
    """Run a single golden case through the shadow-mode path."""

    note = case.get("note", "")
    billed = case.get("billed_codes", [])
    patient_id = case.get("case_id", "eval_patient")

    if offline:
        from backend.api import _demo_shadow_result

        # ``include_fallback=False`` so unmatched cases register as
        # zero-surfaced rather than emitting the E11.22 demo placeholder
        # — the placeholder is intentional in the sales-demo path but
        # would otherwise trip every CHF / COPD case's must_abstain
        # gate. See ``_demo_shadow_result`` for the contract.
        return _demo_shadow_result(
            patient_id=patient_id,
            note=note,
            billed_codes=billed,
            source="eval_offline",
            include_fallback=False,
        )

    # Real-LLM mode. The Agent constructor honors the live LLM provider
    # and BAA tripwire, so this is the same path a pilot customer hits.
    from core.agent import Agent

    agent = Agent()
    raw = agent.handle(
        json.dumps({"note": note, "billed_codes": billed, "patient_id": patient_id}),
        task_type="shadow_mode_rcm",
        tenant_id=uuid.UUID("00000000-0000-0000-0000-0000000000ee"),
    )
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"identified_codes": [], "abstained_codes": [], "summary": raw}


def _extract_codes(result: Dict[str, Any]) -> tuple[List[str], List[str]]:
    """Extract surfaced + abstained code strings from a shadow result."""
    surfaced = [
        item.get("code", "")
        for item in result.get("identified_codes", [])
        if isinstance(item, dict)
    ]
    abstained = [
        item.get("code", "")
        for item in result.get("abstained_codes", [])
        if isinstance(item, dict)
    ]
    return surfaced, abstained


def _extract_suggestions(
    result: Dict[str, Any],
) -> list[Dict[str, Any]]:
    """Extract the full suggestion dicts (with justification) for citation metrics."""
    return [
        item
        for item in result.get("identified_codes", [])
        if isinstance(item, dict) and item.get("code")
    ]


def _load_baseline(path: Path) -> Dict[str, float]:
    if not path.exists():
        logger.warning("Baseline file %s not found; using zero baseline", path)
        return {"precision": 0.0, "recall": 0.0}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise SystemExit(f"Malformed baseline {path}: {e}") from e
    return {
        "precision": float(data.get("precision", 0.0)),
        "recall": float(data.get("recall", 0.0)),
    }


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cases",
        type=Path,
        default=Path("evals/golden"),
        help="Directory of clinician-labeled golden cases.",
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        default=Path("evals/baseline.json"),
        help="Precision / recall baseline for regression check.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional path to write the JSON report.",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Skip the real LLM call (CI default).",
    )
    parser.add_argument(
        "--ci",
        action="store_true",
        help="CI mode: implies --offline (CI has no BAA / live LLM) and "
        "applies the absolute precision/recall floors from "
        "EVAL_PRECISION_FLOOR / EVAL_RECALL_FLOOR on top of the relative "
        "regression gate.",
    )
    parser.add_argument(
        "--tolerance",
        type=float,
        default=0.05,
        help="Allowed precision/recall drop vs baseline before failure.",
    )
    parser.add_argument(
        "--no-regression-gate",
        action="store_true",
        help="Compute metrics but don't fail on regressions (useful for "
        "intentional baseline bumps).",
    )
    args = parser.parse_args(argv)

    # --ci is the canonical CI invocation (build-out A2.3): it never has the
    # BAA / live LLM, so it always runs offline against the demo fallback.
    if args.ci:
        args.offline = True

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    # CI test-mode guard so heavy modules import cleanly without a
    # production .env file present.
    os.environ.setdefault("BUDDI_TEST_MODE", "1")
    os.environ.setdefault("BUDDI_DISABLE_MERKLE_TASK", "1")
    os.environ.setdefault("BUDDI_RATE_LIMIT_DISABLED", "1")

    cases = _load_cases(args.cases)
    logger.info("Loaded %d golden cases from %s", len(cases), args.cases)

    scores: List[CaseScore] = []
    for case in cases:
        result = _shadow_result_for_case(case, offline=args.offline)
        surfaced, abstained = _extract_codes(result)
        suggestions = _extract_suggestions(result)
        scores.append(
            score_case(
                case_id=case.get("case_id", "unknown"),
                surfaced_codes=surfaced,
                abstained_codes=abstained,
                expected_codes=case.get("expected_codes", []),
                must_abstain_codes=case.get("must_abstain_codes", []),
                # P‑B2: citation metrics.
                note=case.get("note", ""),
                surfaced_suggestions=suggestions,
            )
        )

    # Absolute precision/recall floors (build-out A2.2). Default 0.0 (disabled)
    # so the deterministic offline CI run — whose demo-fallback baseline is
    # intentionally low — stays green. Set EVAL_PRECISION_FLOOR /
    # EVAL_RECALL_FLOOR (e.g. 0.60) for the real-LLM golden-set run.
    precision_floor = float(os.getenv("EVAL_PRECISION_FLOOR", "0") or "0")
    recall_floor = float(os.getenv("EVAL_RECALL_FLOOR", "0") or "0")

    summary = aggregate(scores)
    report = {
        "summary": asdict(summary),
        "cases": [asdict(s) for s in scores],
        "config": {
            "cases_dir": str(args.cases),
            "offline": args.offline,
            "ci": args.ci,
            "tolerance": args.tolerance,
            "precision_floor": precision_floor,
            "recall_floor": recall_floor,
        },
    }
    print(json.dumps(report, indent=2, sort_keys=True))

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        logger.info("Wrote report to %s", args.output)

    failures: List[str] = []

    # Absolute floor gate. Always evaluated; default floors of 0.0 never fire.
    if summary.precision < precision_floor:
        failures.append(
            f"precision {summary.precision:.3f} below floor {precision_floor:.2f} "
            "(EVAL_PRECISION_FLOOR)"
        )
    if summary.recall < recall_floor:
        failures.append(
            f"recall {summary.recall:.3f} below floor {recall_floor:.2f} "
            "(EVAL_RECALL_FLOOR)"
        )

    # Relative regression gate + must-abstain hard fail vs the curated baseline.
    if not args.no_regression_gate:
        baseline = _load_baseline(args.baseline)
        failures.extend(
            regression_against_baseline(
                current=summary, baseline=baseline, tolerance=args.tolerance
            )
        )

    if failures:
        for failure in failures:
            logger.error("Eval gate failure: %s", failure)
        return 1
    logger.info("Eval passed: precision=%.3f recall=%.3f", summary.precision, summary.recall)
    return 0


if __name__ == "__main__":
    sys.exit(main())
