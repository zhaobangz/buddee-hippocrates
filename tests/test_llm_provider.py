"""Tests for the build-out A1 LLM-provider guardrails.

Strategy doc §2.2 mandates Anthropic as the primary clinical-reasoning
provider and OpenAI as embeddings-only. Two invariants are checked here:

  1. ``LLM_PROVIDER`` defaults to ``anthropic`` (A1.1).
  2. The OpenAI client used by the RAG path is an embeddings-only guard
     proxy — any non-embedding attribute access (chat/completions/responses)
     raises ``RuntimeError`` rather than silently routing a clinical prompt
     to the wrong vendor and escaping the BAA tripwire (A1.3).

No network, no DB, no PHI.
"""

from __future__ import annotations

import pytest

from core.config import settings
from core.rag_engine import _EmbeddingsOnlyOpenAI, _looks_like_phi_query


def test_llm_provider_defaults_to_anthropic():
    assert settings.LLM_PROVIDER == "anthropic"


class _FakeOpenAI:
    embeddings = "EMBEDDINGS_SURFACE"
    chat = "CHAT_SURFACE"
    completions = "COMPLETIONS_SURFACE"
    responses = "RESPONSES_SURFACE"


def test_embeddings_surface_passes_through():
    guard = _EmbeddingsOnlyOpenAI(_FakeOpenAI())
    assert guard.embeddings == "EMBEDDINGS_SURFACE"


@pytest.mark.parametrize("attr", ["chat", "completions", "responses", "moderations"])
def test_non_embedding_call_raises_runtime_error(attr):
    guard = _EmbeddingsOnlyOpenAI(_FakeOpenAI())
    with pytest.raises(RuntimeError, match="embeddings-only"):
        getattr(guard, attr)


def test_rag_blocks_clinical_note_shaped_embedding_query():
    assert _looks_like_phi_query(
        "67-year-old patient clinical note assessment includes medications"
    )
    assert not _looks_like_phi_query("CMS HCC ICD-10 risk adjustment coding guidelines")
