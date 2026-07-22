"""Unit tests for the P‑B2 citation-accuracy and evidence-quote-coverage metrics."""
from __future__ import annotations

from evals.metrics import (
    CaseScore,
    _is_verbatim_substring,
    aggregate,
    compute_citation_accuracy,
    compute_evidence_quote_coverage,
    score_case,
)


# ---------------------------------------------------------------------------
# _is_verbatim_substring
# ---------------------------------------------------------------------------


def test_verbatim_substring_positive():
    assert _is_verbatim_substring("type 2 diabetes", "67yo with type 2 diabetes and CKD") is True


def test_verbatim_substring_negative():
    assert _is_verbatim_substring("type 2 dm", "67yo with type 2 diabetes and CKD") is False


def test_verbatim_substring_empty_quote():
    assert _is_verbatim_substring("", "some note") is False


def test_verbatim_substring_empty_note():
    assert _is_verbatim_substring("quote", "") is False


def test_verbatim_substring_case_sensitive():
    assert _is_verbatim_substring("Type 2 Diabetes", "type 2 diabetes noted") is False


# ---------------------------------------------------------------------------
# compute_citation_accuracy
# ---------------------------------------------------------------------------


def test_citation_accuracy_all_pass():
    note = "Patient has type 2 diabetes with CKD stage 3a."
    suggestions = [
        {"code": "E11.22", "justification": "type 2 diabetes with CKD"},
        {"code": "N18.31", "justification": "CKD stage 3a"},
    ]
    assert compute_citation_accuracy(suggestions, note) == 1.0


def test_citation_accuracy_half_pass():
    note = "Patient has type 2 diabetes."
    suggestions = [
        {"code": "E11.22", "justification": "type 2 diabetes"},
        {"code": "N18.31", "justification": "CKD stage 3a"},  # not in note
    ]
    assert compute_citation_accuracy(suggestions, note) == 0.5


def test_citation_accuracy_empty_justification_fails():
    note = "Patient has type 2 diabetes."
    suggestions = [
        {"code": "E11.22", "justification": ""},
    ]
    assert compute_citation_accuracy(suggestions, note) == 0.0


def test_citation_accuracy_no_suggestions_is_1():
    assert compute_citation_accuracy([], "any note") == 1.0


def test_citation_accuracy_missing_justification_key():
    note = "Patient has type 2 diabetes."
    suggestions = [
        {"code": "E11.22"},  # no justification key
    ]
    assert compute_citation_accuracy(suggestions, note) == 0.0


# ---------------------------------------------------------------------------
# compute_evidence_quote_coverage
# ---------------------------------------------------------------------------


def test_evidence_quote_coverage_all_have_quotes():
    suggestions = [
        {"code": "E11.22", "justification": "diabetes noted"},
        {"code": "N18.31", "justification": "CKD stage 3a"},
    ]
    assert compute_evidence_quote_coverage(suggestions) == 1.0


def test_evidence_quote_coverage_half_missing():
    suggestions = [
        {"code": "E11.22", "justification": "diabetes noted"},
        {"code": "N18.31"},
    ]
    assert compute_evidence_quote_coverage(suggestions) == 0.5


def test_evidence_quote_coverage_all_empty():
    suggestions = [
        {"code": "E11.22", "justification": ""},
        {"code": "N18.31", "justification": "  "},
    ]
    assert compute_evidence_quote_coverage(suggestions) == 0.0


def test_evidence_quote_coverage_no_suggestions_is_1():
    assert compute_evidence_quote_coverage([]) == 1.0


# ---------------------------------------------------------------------------
# score_case with citation metrics
# ---------------------------------------------------------------------------


def test_score_case_includes_citation_metrics():
    note = "67yo male with type 2 diabetes and CKD stage 3a."
    suggestions = [
        {"code": "E11.22", "justification": "type 2 diabetes"},
        {"code": "N18.31", "justification": "CKD stage 3a"},
    ]
    score = score_case(
        case_id="test",
        surfaced_codes=["E11.22", "N18.31"],
        abstained_codes=[],
        expected_codes=["E11.22", "N18.31"],
        note=note,
        surfaced_suggestions=suggestions,
    )
    assert score.citation_accuracy == 1.0
    assert score.evidence_quote_coverage == 1.0
    assert score.precision == 1.0
    assert score.recall == 1.0


def test_score_case_citation_defaults_to_1_when_no_note():
    score = score_case(
        case_id="test",
        surfaced_codes=["E11.22"],
        abstained_codes=[],
        expected_codes=["E11.22"],
    )
    # Without note + suggestions, citation metrics default to 1.0.
    assert score.citation_accuracy == 1.0
    assert score.evidence_quote_coverage == 1.0


def test_score_case_citation_partial():
    note = "Patient has diabetes."
    suggestions = [
        {"code": "E11.22", "justification": "diabetes"},       # verbatim ✓
        {"code": "I12.9", "justification": "hypertensive"},    # verbatim ✗
    ]
    score = score_case(
        case_id="test",
        surfaced_codes=["E11.22", "I12.9"],
        abstained_codes=[],
        expected_codes=["E11.22", "I12.9"],
        note=note,
        surfaced_suggestions=suggestions,
    )
    assert score.citation_accuracy == 0.5
    assert score.evidence_quote_coverage == 1.0  # both have non-empty justifications


# ---------------------------------------------------------------------------
# aggregate with citation metrics
# ---------------------------------------------------------------------------


def test_aggregate_averages_citation_metrics():
    s1 = CaseScore(
        case_id="a", precision=1.0, recall=1.0, abstain_rate=0.0,
        citation_accuracy=1.0, evidence_quote_coverage=1.0,
    )
    s2 = CaseScore(
        case_id="b", precision=0.5, recall=0.5, abstain_rate=0.0,
        citation_accuracy=0.0, evidence_quote_coverage=0.5,
    )
    agg = aggregate([s1, s2])
    assert agg.citation_accuracy == 0.5
    assert agg.evidence_quote_coverage == 0.75
