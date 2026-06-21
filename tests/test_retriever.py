"""Tests for the build-out B4.3 Retriever protocol.

The pluggable interface lets pgvector be swapped for Turbopuffer without
touching call sites. We assert the concrete engines satisfy the protocol and
that the disabled stub returns no chunks.
"""

from __future__ import annotations

import pytest

from core.rag_engine import RAGEngine, RetrievedChunk, Retriever, StubRAGEngine


def test_engines_satisfy_retriever_protocol():
    # runtime_checkable Protocol — verifies the retrieve() method is present.
    assert isinstance(StubRAGEngine(), Retriever)
    assert isinstance(RAGEngine(), Retriever)


@pytest.mark.asyncio
async def test_stub_retrieve_returns_empty():
    chunks = await StubRAGEngine().retrieve([0.0] * 1536, top_k=3, tenant_id=None)
    assert chunks == []


def test_retrieved_chunk_shape():
    c = RetrievedChunk(chunk_id="abc", text="guideline text", relevance_score=0.91)
    assert c.chunk_id == "abc"
    assert c.relevance_score == 0.91
