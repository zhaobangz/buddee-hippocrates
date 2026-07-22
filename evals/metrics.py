"""Precision / recall / abstain-rate / citation math for the eval harness.

Kept deliberately small and dependency-free so the regression gate in
CI does not pull in pandas / sklearn. The numbers we care about are:

    precision_top3        = TP / (TP + FP), restricted to the top-3 surfaced codes.
    recall_top3           = TP / (TP + FN), restricted to expected_codes.
    abstain_rate          = abstained_count / (surfaced_count + abstained_count)
    citation_accuracy     = fraction of surfaced suggestions whose justification
                            is a verbatim substring of the source note.
    evidence_quote_coverage = fraction of surfaced suggestions that carry a
                              non-empty justification string.

A "TP" is a surfaced code that appears in ``expected_codes``. A "FP" is a
surfaced code that does not (and is not flagged as
``must_abstain_codes`` — that is treated as a separate, harder fail).

We intentionally compute precision and recall *per case* and average,
rather than micro-averaging across the whole set, so a single
high-volume case can't dominate the metric.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Sequence

# ---------------------------------------------------------------------------
# Citation helpers (P‑B2)
# ---------------------------------------------------------------------------


def _is_verbatim_substring(quote: str, note: str) -> bool:
    """Check whether *quote* appears verbatim inside *note*.

    Comparison is case‑sensitive and whitespace‑sensitive — a citation
    must be an exact substring, not a paraphrase. This is the stricter
    of the two citation checks.
    """
    if not quote or not note:
        return False
    return quote in note


def compute_citation_accuracy(
    surfaced_suggestions: Sequence[Dict[str, Any]],
    note: str,
) -> float:
    """Fraction of surfaced suggestions whose justification is verbatim in the note.

    Each suggestion dict is expected to have a ``justification`` key (the
    evidence quote). A suggestion passes citation accuracy if its
    justification is a non‑empty verbatim substring of the source note.

    Returns 1.0 when there are no surfaced suggestions (nothing to cite).
    """
    if not surfaced_suggestions:
        return 1.0
    passed = 0
    for s in surfaced_suggestions:
        justification = (s.get("justification") or "").strip()
        if justification and _is_verbatim_substring(justification, note):
            passed += 1
    return passed / len(surfaced_suggestions)


def compute_evidence_quote_coverage(
    surfaced_suggestions: Sequence[Dict[str, Any]],
) -> float:
    """Fraction of surfaced suggestions that carry a non‑empty justification.

    The manual §6.1 target is 100% — every surfaced code must cite its
    evidence. Returns 1.0 when there are no surfaced suggestions.
    """
    if not surfaced_suggestions:
        return 1.0
    with_quote = sum(
        1 for s in surfaced_suggestions if (s.get("justification") or "").strip()
    )
    return with_quote / len(surfaced_suggestions)


# ---------------------------------------------------------------------------
# Core scoring data structures
# ---------------------------------------------------------------------------


@dataclass
class CaseScore:
    case_id: str
    precision: float
    recall: float
    abstain_rate: float
    citation_accuracy: float = 1.0
    evidence_quote_coverage: float = 1.0
    must_abstain_violations: List[str] = field(default_factory=list)
    surfaced: List[str] = field(default_factory=list)
    expected: List[str] = field(default_factory=list)
    abstained: List[str] = field(default_factory=list)


@dataclass
class AggregateScore:
    case_count: int
    precision: float
    recall: float
    abstain_rate: float
    citation_accuracy: float
    evidence_quote_coverage: float
    must_abstain_violations_total: int
    violating_case_ids: List[str]


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
    # P‑B2: citation metrics require the source note + full suggestion objects.
    note: str = "",
    surfaced_suggestions: Sequence[Dict[str, Any]] | None = None,
) -> CaseScore:
    """Score a single golden case.

    The new ``note`` and ``surfaced_suggestions`` parameters enable the
    citation‑accuracy and evidence‑quote‑coverage metrics (P‑B2). When
    omitted, both metrics default to 1.0 — the pre‑B2 behaviour is
    preserved.
    """

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

    # P‑B2: citation metrics.
    suggestions = list(surfaced_suggestions or [])[:top_k]
    citation_accuracy = compute_citation_accuracy(suggestions, note)
    evidence_quote_coverage = compute_evidence_quote_coverage(suggestions)

    return CaseScore(
        case_id=case_id,
        precision=precision,
        recall=recall,
        abstain_rate=abstain_rate,
        citation_accuracy=citation_accuracy,
        evidence_quote_coverage=evidence_quote_coverage,
        must_abstain_violations=violations,
        surfaced=surfaced,
        expected=expected,
        abstained=abstained,
    )


def aggregate(scores: Sequence[CaseScore]) -> AggregateScore:
    """Average per-case scores; surface every must-abstain violation."""

    if not scores:
        return AggregateScore(
            case_count=0,
            precision=0.0,
            recall=0.0,
            abstain_rate=0.0,
            citation_accuracy=0.0,
            evidence_quote_coverage=0.0,
            must_abstain_violations_total=0,
            violating_case_ids=[],
        )

    n = len(scores)
    precision = sum(s.precision for s in scores) / n
    recall = sum(s.recall for s in scores) / n
    abstain_rate = sum(s.abstain_rate for s in scores) / n
    citation_accuracy = sum(s.citation_accuracy for s in scores) / n
    evidence_quote_coverage = sum(s.evidence_quote_coverage for s in scores) / n
    violations = [s.case_id for s in scores if s.must_abstain_violations]
    total_violations = sum(len(s.must_abstain_violations) for s in scores)
    return AggregateScore(
        case_count=n,
        precision=precision,
        recall=recall,
        abstain_rate=abstain_rate,
        citation_accuracy=citation_accuracy,
        evidence_quote_coverage=evidence_quote_coverage,
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
    # P‑B2: citation metrics are advisory only — they warn but do not fail the gate.
    baseline_citation = float(baseline.get("citation_accuracy", 0.0))
    baseline_coverage = float(baseline.get("evidence_quote_coverage", 0.0))

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

    # P‑B2: citation metrics are advisory — warn on drop, never block the gate.
    if current.citation_accuracy + tolerance < baseline_citation:
        failures.append(
            f"[advisory] citation_accuracy regressed by more than {tolerance:.0%} "
            f"(current={current.citation_accuracy:.3f}, baseline={baseline_citation:.3f})"
        )
    if current.evidence_quote_coverage + tolerance < baseline_coverage:
        failures.append(
            f"[advisory] evidence_quote_coverage regressed by more than {tolerance:.0%} "
            f"(current={current.evidence_quote_coverage:.3f}, baseline={baseline_coverage:.3f})"
        )

    return failures


__all__ = [
    "AggregateScore",
    "CaseScore",
    "aggregate",
    "compute_citation_accuracy",
    "compute_evidence_quote_coverage",
    "regression_against_baseline",
    "score_case",
]
