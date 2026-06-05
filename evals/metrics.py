"""Precision / recall / abstain-rate math for the eval harness.

Kept deliberately small and dependency-free so the regression gate in
CI does not pull in pandas / sklearn. The numbers we care about are:

    precision_top3 = TP / (TP + FP), restricted to the top-3 surfaced codes.
    recall_top3    = TP / (TP + FN), restricted to expected_codes.
    abstain_rate   = abstained_count / (surfaced_count + abstained_count)

A "TP" is a surfaced code that appears in ``expected_codes``. A "FP" is a
surfaced code that does not (and is not flagged as
``must_abstain_codes`` — that is treated as a separate, harder fail).

We intentionally compute precision and recall *per case* and average,
rather than micro-averaging across the whole set, so a single
high-volume case can't dominate the metric.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Sequence


@dataclass
class CaseScore:
    case_id: str
    precision: float
    recall: float
    abstain_rate: float
    must_abstain_violations: List[str]
    surfaced: List[str]
    expected: List[str]
    abstained: List[str]


def _normalize(codes: Iterable[str]) -> List[str]:
    """Strip whitespace and uppercase so 'e11.22' == 'E11.22'."""

    return [c.strip().upper() for c in codes if c and isinstance(c, str)]


def score_case(
    *,
    case_id: str,
    surfaced_codes: Sequence[str],
    abstained_codes: Sequence[str],
    expected_codes: Sequence[str],
    must_abstain_codes: Sequence[str] = (),
    top_k: int = 3,
) -> CaseScore:
    """Score a single golden case."""

    surfaced = _normalize(surfaced_codes)[:top_k]
    expected = _normalize(expected_codes)
    abstained = _normalize(abstained_codes)
    must_abstain = set(_normalize(must_abstain_codes))

    expected_set = set(expected)
    surfaced_set = set(surfaced)

    tp = len(surfaced_set & expected_set)
    fp = len(surfaced_set - expected_set)
    fn = len(expected_set - surfaced_set)
    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0

    total_codes = len(surfaced) + len(abstained)
    abstain_rate = len(abstained) / total_codes if total_codes else 0.0

    violations = sorted(surfaced_set & must_abstain)

    return CaseScore(
        case_id=case_id,
        precision=precision,
        recall=recall,
        abstain_rate=abstain_rate,
        must_abstain_violations=violations,
        surfaced=surfaced,
        expected=expected,
        abstained=abstained,
    )


@dataclass
class AggregateScore:
    case_count: int
    precision: float
    recall: float
    abstain_rate: float
    must_abstain_violations_total: int
    violating_case_ids: List[str]


def aggregate(scores: Sequence[CaseScore]) -> AggregateScore:
    """Average per-case scores; surface every must-abstain violation."""

    if not scores:
        return AggregateScore(
            case_count=0,
            precision=0.0,
            recall=0.0,
            abstain_rate=0.0,
            must_abstain_violations_total=0,
            violating_case_ids=[],
        )

    precision = sum(s.precision for s in scores) / len(scores)
    recall = sum(s.recall for s in scores) / len(scores)
    abstain_rate = sum(s.abstain_rate for s in scores) / len(scores)
    violations = [s.case_id for s in scores if s.must_abstain_violations]
    total_violations = sum(len(s.must_abstain_violations) for s in scores)
    return AggregateScore(
        case_count=len(scores),
        precision=precision,
        recall=recall,
        abstain_rate=abstain_rate,
        must_abstain_violations_total=total_violations,
        violating_case_ids=violations,
    )


def regression_against_baseline(
    *,
    current: AggregateScore,
    baseline: Dict[str, float],
    tolerance: float = 0.05,
) -> List[str]:
    """Return a list of human-readable failure reasons (empty = pass)."""

    failures: List[str] = []
    baseline_precision = float(baseline.get("precision", 0.0))
    baseline_recall = float(baseline.get("recall", 0.0))
    if current.precision + tolerance < baseline_precision:
        failures.append(
            f"precision regressed by more than {tolerance:.0%} "
            f"(current={current.precision:.3f}, baseline={baseline_precision:.3f})"
        )
    if current.recall + tolerance < baseline_recall:
        failures.append(
            f"recall regressed by more than {tolerance:.0%} "
            f"(current={current.recall:.3f}, baseline={baseline_recall:.3f})"
        )
    if current.must_abstain_violations_total:
        failures.append(
            f"{current.must_abstain_violations_total} must-abstain violation(s) "
            f"in cases: {', '.join(current.violating_case_ids)}"
        )
    return failures


__all__ = [
    "AggregateScore",
    "CaseScore",
    "aggregate",
    "regression_against_baseline",
    "score_case",
]
