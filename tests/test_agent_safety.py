"""Tests for the §7.2 Risk #2 anti-hallucination controls in ``core/agent.py``.

Two layers guard against the Existential-Risk-#2 failure mode (a hallucinated
HCC code gets approved and submitted, triggering a False Claims Act exposure):

  1. ``_apply_safety_floor`` — a cheap deterministic gate: drop any code below
     the confidence floor or lacking a verbatim evidence quote.
  2. ``_judge_suggestions`` — an independent LLM second-opinion pass for codes
     in the uncertain band ``[floor, threshold)``. Fail-closed: only a "yes"
     verdict survives; judge errors abstain the code.

Both functions are pure (the judge takes the LLM as a parameter), so we test
them with hand-built ``IdentifiedCode`` objects and a fake LLM — no network,
no PHI, no DB.
"""

from __future__ import annotations

import pytest

from core import agent
from core.schemas import IdentifiedCode, JudgeVerdict


def _code(code, *, confidence, justification="documented in note"):
    return IdentifiedCode(
        code=code,
        description=f"desc {code}",
        justification=justification,
        est_value=11000.0,
        confidence=confidence,
    )


# ---------------------------------------------------------------------------
# Confidence floor + mandatory evidence
# ---------------------------------------------------------------------------


def test_safety_floor_drops_below_floor_codes():
    codes = [_code("E11.22", confidence=0.95), _code("I12.9", confidence=0.40)]
    surfaced, abstained = agent._apply_safety_floor(codes, floor=0.70)
    assert [c.code for c in surfaced] == ["E11.22"]
    assert len(abstained) == 1
    assert abstained[0]["code"] == "I12.9"
    assert abstained[0]["_abstain_reason"] == "below_confidence_floor"


def test_safety_floor_drops_codes_without_evidence_quote():
    codes = [_code("E11.22", confidence=0.95, justification="   ")]
    surfaced, abstained = agent._apply_safety_floor(codes, floor=0.70)
    assert surfaced == []
    assert abstained[0]["_abstain_reason"] == "missing_evidence_quote"


def test_safety_floor_surfaces_well_supported_codes():
    codes = [_code("E11.22", confidence=0.90, justification="A1c 9.2, on insulin")]
    surfaced, abstained = agent._apply_safety_floor(codes, floor=0.70)
    assert [c.code for c in surfaced] == ["E11.22"]
    assert abstained == []


# ---------------------------------------------------------------------------
# LLM-as-judge second pass
# ---------------------------------------------------------------------------


class _FakeLLM:
    """Returns a scripted ``JudgeVerdict`` and records prompts it received."""

    def __init__(self, verdict="yes", *, raise_exc=None):
        self._verdict = verdict
        self._raise = raise_exc
        self.calls = 0
        self.prompts = []

    def ask_llm_structured(self, prompt, schema, *, model_tier="reasoning"):
        self.calls += 1
        self.prompts.append(prompt)
        if self._raise is not None:
            raise self._raise
        assert schema is JudgeVerdict
        return JudgeVerdict(code="X", verdict=self._verdict, rationale="test")


def test_judge_skips_high_confidence_codes():
    """Codes at/above the threshold bypass the judge entirely (no LLM call)."""
    llm = _FakeLLM(verdict="no")  # would reject if consulted
    codes = [_code("E11.22", confidence=0.92)]
    confirmed, rejected = agent._judge_suggestions(llm, "note", codes, threshold=0.85)
    assert [c.code for c in confirmed] == ["E11.22"]
    assert rejected == []
    assert llm.calls == 0  # high-confidence code never hits the judge


def test_judge_confirms_on_yes_verdict():
    llm = _FakeLLM(verdict="yes")
    codes = [_code("I12.9", confidence=0.74)]
    confirmed, rejected = agent._judge_suggestions(llm, "note", codes, threshold=0.85)
    assert [c.code for c in confirmed] == ["I12.9"]
    assert rejected == []
    assert llm.calls == 1


@pytest.mark.parametrize("verdict", ["no", "abstain"])
def test_judge_rejects_uncertain_codes(verdict):
    llm = _FakeLLM(verdict=verdict)
    codes = [_code("I12.9", confidence=0.74)]
    confirmed, rejected = agent._judge_suggestions(llm, "note", codes, threshold=0.85)
    assert confirmed == []
    assert rejected[0]["code"] == "I12.9"
    assert rejected[0]["_abstain_reason"] == f"judge_{verdict}"


def test_judge_fails_closed_on_llm_error():
    """A judge that errors (e.g. BAA guard, timeout) must abstain, not surface."""
    llm = _FakeLLM(raise_exc=RuntimeError("provider exploded"))
    codes = [_code("I12.9", confidence=0.74)]
    confirmed, rejected = agent._judge_suggestions(llm, "note", codes, threshold=0.85)
    assert confirmed == []
    assert rejected[0]["_abstain_reason"] == "judge_error"


def test_judge_prompt_wraps_note_for_baa_classification():
    """The judge prompt must wrap the note so the BAA tripwire treats it as PHI."""
    prompt = agent._judge_prompt("patient note text", "E11.22", "DM w/ CKD", "A1c 9.2")
    assert "<clinical_note>" in prompt and "</clinical_note>" in prompt
    assert "E11.22" in prompt
    assert "patient note text" in prompt
