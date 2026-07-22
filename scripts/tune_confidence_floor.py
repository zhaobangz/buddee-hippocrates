#!/usr/bin/env python3
"""
Confidence‑floor tuning sweep for the HCC suggestion eval harness.

Runs the full eval at floor ∈ {0.60, 0.65, 0.70, 0.75, 0.80} and produces
a precision/recall/F1 + abstain‑rate table. Recommends the F1‑maximizing
floor. The chosen value is written to ``docs/RETRO/confidence_tuning.md``
as a decision record.

Usage:
    # Offline (deterministic stub — wiring test only):
    python scripts/tune_confidence_floor.py --offline

    # Real‑LLM (requires ANTHROPIC_API_KEY + labeled golden set):
    python scripts/tune_confidence_floor.py --cases evals/golden/v1

    # Write decision record:
    python scripts/tune_confidence_floor.py --cases evals/golden/v1 --write-decision

This script must NOT require PHI or live PHI keys — it runs on the
synthetic golden set only. The floor change itself is a one‑line edit in
``core/agent.py`` and is NOT applied by this script.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure the eval harness is importable.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evals.metrics import CaseScore, aggregate, score_case
from evals.run_eval import _extract_codes, _extract_suggestions, _load_cases


FLOORS = [0.60, 0.65, 0.70, 0.75, 0.80]

# The one‑line change site in core/agent.py.
_AGENT_FLOOR_PATH = "core/agent.py"
_FLOOR_LINE_MARKER = "BUDDI_HCC_CONFIDENCE_FLOOR"


@dataclass
class FloorResult:
    floor: float
    precision: float
    recall: float
    f1: float
    abstain_rate: float
    citation_accuracy: float
    evidence_quote_coverage: float


def _run_eval_at_floor(
    cases: List[Dict[str, Any]],
    floor: float,
    *,
    offline: bool,
) -> FloorResult:
    """Run the eval harness at a specific confidence floor.

    In offline mode the floor does not affect the deterministic fallback
    (there is no confidence threshold on rule‑based suggestions). The
    real‑LLM path does enforce it — the agent abstains suggestions below
    the floor.
    """
    os.environ["BUDDI_HCC_CONFIDENCE_FLOOR"] = str(floor)

    scores: List[CaseScore] = []
    for case in cases:
        if offline:
            from backend.api import _demo_shadow_result

            result = _demo_shadow_result(
                patient_id=case.get("case_id", "eval"),
                note=case.get("note", ""),
                billed_codes=case.get("billed_codes", []),
                source="tuning_sweep",
                include_fallback=False,
            )
        else:
            from core.agent import Agent

            agent = Agent()
            raw = agent.handle(
                json.dumps({
                    "note": case.get("note", ""),
                    "billed_codes": case.get("billed_codes", []),
                    "patient_id": case.get("case_id", "eval"),
                }),
                task_type="shadow_mode_rcm",
                tenant_id=uuid.UUID("00000000-0000-0000-0000-0000000000ee"),
            )
            try:
                result = json.loads(raw)
            except json.JSONDecodeError:
                result = {"identified_codes": [], "abstained_codes": []}

        surfaced, abstained = _extract_codes(result)
        suggestions = _extract_suggestions(result)
        scores.append(
            score_case(
                case_id=case.get("case_id", "unknown"),
                surfaced_codes=surfaced,
                abstained_codes=abstained,
                expected_codes=case.get("expected_codes", []),
                must_abstain_codes=case.get("must_abstain_codes", []),
                note=case.get("note", ""),
                surfaced_suggestions=suggestions,
            )
        )

    agg = aggregate(scores)
    f1 = (
        2 * agg.precision * agg.recall / (agg.precision + agg.recall)
        if (agg.precision + agg.recall) > 0
        else 0.0
    )
    return FloorResult(
        floor=floor,
        precision=agg.precision,
        recall=agg.recall,
        f1=f1,
        abstain_rate=agg.abstain_rate,
        citation_accuracy=agg.citation_accuracy,
        evidence_quote_coverage=agg.evidence_quote_coverage,
    )


def _print_table(results: List[FloorResult]) -> None:
    print()
    header = (
        f"  {'Floor':>5}  {'Precision':>9}  {'Recall':>9}  {'F1':>9}  "
        f"{'Abstain%':>8}  {'CiteAcc':>7}  {'EvQuote%':>8}"
    )
    print(header)
    print(f"  {'─' * (len(header) - 2)}")
    for r in results:
        print(
            f"  {r.floor:>5.2f}  "
            f"{r.precision:>9.4f}  {r.recall:>9.4f}  {r.f1:>9.4f}  "
            f"{r.abstain_rate:>8.1%}  {r.citation_accuracy:>7.4f}  "
            f"{r.evidence_quote_coverage:>8.1%}"
        )
    print()


def _best_floor(results: List[FloorResult]) -> FloorResult:
    return max(results, key=lambda r: r.f1)


def _write_decision_record(results: List[FloorResult], best: FloorResult, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Confidence‑Floor Tuning Decision Record",
        "",
        "**Date:** (fill in after sweep)",
        "**Golden set:** (fill in — evals/golden/v1/ count)",
        "**LLM mode:** (offline / live — fill in)",
        "",
        "## Sweep results",
        "",
        "| Floor | Precision | Recall | F1 | Abstain % | Cite Acc | Ev Quote % |",
        "|-------|-----------|--------|----|-----------|----------|-----------|",
    ]
    for r in results:
        lines.append(
            f"| {r.floor:.2f} | {r.precision:.4f} | {r.recall:.4f} | "
            f"{r.f1:.4f} | {r.abstain_rate:.1%} | {r.citation_accuracy:.4f} | "
            f"{r.evidence_quote_coverage:.1%} |"
        )
    lines += [
        "",
        "## Recommendation",
        "",
        f"**Best floor (F1‑maximizing):** `{best.floor:.2f}`",
        f"**F1 at best floor:** `{best.f1:.4f}`",
        f"**Precision at best floor:** `{best.precision:.4f}`",
        f"**Recall at best floor:** `{best.recall:.4f}`",
        "",
        "## Change site",
        "",
        f"The floor is read from `BUDDI_HCC_CONFIDENCE_FLOOR` in `{_AGENT_FLOOR_PATH}`.",
        "To apply the recommended floor, change the default in `.env.example` and",
        "the agent's fallback value. This is gated on:",
        "",
        "1. ✅ LLM‑on eval is green at the new floor",
        "2. ✅ Clinician advisor has reviewed the swept golden set",
        "3. ✅ Decision record is filed (this document)",
        "",
        "**Do not change the clinical prompt path without a green LLM‑on eval**",
        "(manual §4.4).",
        "",
    ]
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n📄  Decision record written to {out}")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Confidence‑floor tuning sweep for the Buddi eval harness."
    )
    parser.add_argument(
        "--cases",
        type=Path,
        default=Path("evals/golden"),
        help="Directory of golden cases (default: evals/golden).",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Use the deterministic fallback (no LLM call).",
    )
    parser.add_argument(
        "--write-decision",
        type=Path,
        default=None,
        const=Path("docs/RETRO/confidence_tuning.md"),
        nargs="?",
        help="Write the decision record to the given path (default: docs/RETRO/confidence_tuning.md).",
    )
    args = parser.parse_args(argv)

    os.environ.setdefault("BUDDI_TEST_MODE", "1")
    os.environ.setdefault("BUDDI_DISABLE_MERKLE_TASK", "1")
    os.environ.setdefault("BUDDI_RATE_LIMIT_DISABLED", "1")

    cases = _load_cases(args.cases)
    print(f"📋  Loaded {len(cases)} golden cases from {args.cases}")
    print(f"🧪  Testing floors: {[f'{f:.2f}' for f in FLOORS]}")
    if args.offline:
        print("⚠️   OFFLINE mode — floor does not affect deterministic fallback")

    results: List[FloorResult] = []
    for floor in FLOORS:
        result = _run_eval_at_floor(cases, floor, offline=args.offline)
        results.append(result)
        print(
            f"    floor={floor:.2f}  "
            f"p={result.precision:.4f}  r={result.recall:.4f}  "
            f"f1={result.f1:.4f}"
        )

    _print_table(results)
    best = _best_floor(results)
    print(f"🏆  Best floor (F1‑max): {best.floor:.2f}  (F1={best.f1:.4f})")
    print(f"    Precision: {best.precision:.4f}  Recall: {best.recall:.4f}")
    print()
    print(
        "➡️   To apply: set BUDDI_HCC_CONFIDENCE_FLOOR=<value> in .env "
        "and re‑run with real LLM + labeled set."
    )
    print(
        "    The change site is in core/agent.py — search for "
        f"{_FLOOR_LINE_MARKER}."
    )

    if args.write_decision:
        _write_decision_record(results, best, Path(args.write_decision))

    return 0


if __name__ == "__main__":
    sys.exit(main())
