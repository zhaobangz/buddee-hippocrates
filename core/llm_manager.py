"""Buddi LLM Manager — Anthropic-primary, OpenAI-fallback, no LangChain.

Implements the strategic-manual directive (§2.2 week 1–2 and BUILD_PLAN.md
strategic bet #1):

    Anthropic-first LLM stack with OpenAI as fallback. Claude Opus 4.6 for
    clinical reasoning and safety arbitration; Claude Sonnet 4.6 for
    high-volume coding suggestions; OpenAI text-embedding-3-large for
    embeddings only (no PHI in the prompt path on OpenAI until you have a
    current BAA on file).

Public surface (stable — ``core/agent.py`` depends on these):

    * ``LLMManager.ask_llm(prompt)``               → str
    * ``LLMManager.ask_llm_async(prompt)``         → str
    * ``LLMManager.ask_llm_structured(prompt, S)`` → S (pydantic model)
    * ``LLMManager.ask_llm_structured_async(...)`` → S (pydantic model)

Provider selection is driven by ``Config.LLM_PROVIDER`` (``"anthropic"``
recommended for production, ``"openai"`` retained for legacy
deployments). When ``anthropic`` is selected but the SDK / API key is
missing we fall back to OpenAI with a logged warning rather than
silently producing wrong output.

BAA tripwire (manual §7.2 Risk #1 mitigation):

    If ``BUDDI_BAA_CONFIRMED`` is not ``"1"`` (the default), any prompt
    that looks like real PHI is refused at the LLM boundary. Two
    heuristics drive the refusal:

      * ``len(prompt) > BUDDI_BAA_MAX_PROMPT_BYTES`` (default 200 bytes)
      * Prompt contains ``<clinical_note>`` or ``<clinical_context>``
        delimiters (the canonical wrappers from ``core/agent.py``).

    This is a *fail-closed* guard: better to break the demo than to
    leak ePHI to a provider whose BAA paperwork has not landed yet. The
    operator UI is expected to surface the resulting error so the
    on-call human can resolve the BAA gap.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, Dict, Optional

import httpx

from core.config import Config

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class RetryError(RuntimeError):
    """Raised when a retryable LLM provider failure persists after retry."""


class BAAGuardError(RuntimeError):
    """Raised when the BAA tripwire (§7.2) blocks an LLM call.

    The caller should surface this to operations rather than retrying —
    no retry policy resolves a missing Business Associate Agreement.
    """


# ---------------------------------------------------------------------------
# Provider abstraction
# ---------------------------------------------------------------------------


_CLINICAL_NOTE_DELIMITERS = ("<clinical_note>", "<clinical_context>")


def _baa_guard(prompt: str) -> None:
    """Refuse the call if real-PHI heuristics fire and the BAA is unconfirmed.

    Configuration:
      * ``BUDDI_BAA_CONFIRMED=1`` — disable the guard. Set this only
        after both the LLM provider BAA *and* the tenant's BAA are filed.
      * ``BUDDI_BAA_MAX_PROMPT_BYTES`` — max prompt size (bytes) allowed
        through when the guard is active. Defaults to 200, which is large
        enough for intent-detection scaffolding and demo strings but too
        small for a real clinical note.
    """

    if os.getenv("BUDDI_BAA_CONFIRMED", "").strip() == "1":
        return
    try:
        max_bytes = int(os.getenv("BUDDI_BAA_MAX_PROMPT_BYTES", "200"))
    except ValueError:
        max_bytes = 200

    payload_bytes = len(prompt.encode("utf-8"))
    if payload_bytes > max_bytes:
        raise BAAGuardError(
            "BAA tripwire: prompt exceeds the unconfirmed-BAA byte cap "
            f"({payload_bytes} > {max_bytes}). Set BUDDI_BAA_CONFIRMED=1 only "
            "after the LLM provider and tenant BAAs are filed (see "
            "docs/COMPLIANCE/baa_status.md)."
        )
    if any(token in prompt for token in _CLINICAL_NOTE_DELIMITERS):
        raise BAAGuardError(
            "BAA tripwire: prompt contains a <clinical_note>/<clinical_context> "
            "delimiter, which signals a real PHI payload. Refusing to send to "
            "the LLM provider until BUDDI_BAA_CONFIRMED=1 is set."
        )


def _resolve_provider() -> str:
    """Resolve the configured provider, normalised to ``anthropic`` / ``openai``."""

    raw = (getattr(Config, "LLM_PROVIDER", "") or os.getenv("LLM_PROVIDER", "")).strip().lower()
    if raw in {"anthropic", "claude"}:
        return "anthropic"
    return "openai"


def _resolve_model_for_provider(provider: str) -> str:
    """Choose a sensible default model per provider, overridable via Config."""

    explicit = (getattr(Config, "LLM_MODEL", "") or os.getenv("LLM_MODEL", "")).strip()
    if explicit and provider == "anthropic" and explicit.startswith("claude"):
        return explicit
    if explicit and provider == "openai" and (explicit.startswith("gpt") or explicit.startswith("o")):
        return explicit
    if provider == "anthropic":
        return os.getenv("ANTHROPIC_MODEL", "claude-opus-4-5")
    return explicit or "gpt-4-turbo"


def _anthropic_api_key() -> str:
    return (
        os.getenv("ANTHROPIC_API_KEY", "").strip()
        or getattr(Config, "ANTHROPIC_API_KEY", "")
        or ""
    )


def _openai_api_key() -> str:
    return (
        os.getenv("OPENAI_API_KEY", "").strip()
        or getattr(Config, "LLM_API_KEY", "")
        or os.getenv("LLM_API_KEY", "").strip()
        or ""
    )


# ---------------------------------------------------------------------------
# JSON extraction (replaces LangChain's structured-output coupling)
# ---------------------------------------------------------------------------


def _extract_json_object(raw: str) -> str:
    """Extract the first JSON object substring from a free-text response.

    Anthropic Claude does not have OpenAI's ``response_format=json_object``
    forcing mode, so we ask the model for JSON and then defensively pull
    the first balanced-brace span. This is intentionally simple — if the
    extracted string fails ``pydantic`` validation, the caller treats it
    as an error and either retries or falls back.
    """

    raw = raw.strip()
    if not raw:
        raise ValueError("Empty LLM response")
    # Strip a leading ``` fenced block if present.
    if raw.startswith("```"):
        raw = raw.strip("`")
        # Drop a leading language hint like ``json``.
        nl = raw.find("\n")
        if nl != -1:
            raw = raw[nl + 1 :]
    # Find the first balanced JSON object. Pure regex can't do recursive
    # balancing in Python's stdlib, so we do a manual scan that's correct
    # for the JSON our prompts return.
    start = raw.find("{")
    if start == -1:
        return raw  # Let pydantic surface the parse error.
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(raw)):
        ch = raw[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return raw[start : i + 1]
    return raw[start:]


# ---------------------------------------------------------------------------
# Provider transports
# ---------------------------------------------------------------------------


async def _anthropic_chat(
    client: httpx.AsyncClient,
    *,
    api_key: str,
    model: str,
    prompt: str,
    structured: bool,
) -> str:
    """Single call to the Anthropic Messages API.

    Uses the public REST surface directly — keeps the dependency graph
    small and gives us full control over the headers / version pinning,
    which BUILD_PLAN.md flagged as preferable to LangChain wrappers.
    """

    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    system_msg = (
        "You are a clinical revenue integrity assistant. Reply in valid JSON only."
        if structured
        else "You are a clinical revenue integrity assistant."
    )
    payload = {
        "model": model,
        "max_tokens": 1500,
        "temperature": 0.1 if structured else 0.2,
        "system": system_msg,
        "messages": [{"role": "user", "content": prompt}],
    }
    response = await client.post(url, json=payload, headers=headers)
    response.raise_for_status()
    body = response.json()
    # Anthropic returns content as a list of blocks; concatenate the
    # ``text`` blocks. Tool-use blocks are not used here.
    content_blocks = body.get("content") or []
    text_parts = [
        block.get("text", "")
        for block in content_blocks
        if isinstance(block, dict) and block.get("type") == "text"
    ]
    return "".join(text_parts).strip()


async def _openai_chat(
    client: httpx.AsyncClient,
    *,
    api_key: str,
    model: str,
    prompt: str,
    structured: bool,
) -> str:
    """Single call to the OpenAI Chat Completions API (fallback only).

    Retained so deployments without an Anthropic key keep working in
    dev / CI. The BAA-tripwire guard sits *before* this call, so a real
    PHI prompt cannot reach OpenAI unless BUDDI_BAA_CONFIRMED=1.
    """

    url = getattr(Config, "LLM_API_URL", "") or "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "content-type": "application/json"}
    payload: Dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1 if structured else 0.2,
    }
    if structured:
        # OpenAI supports a JSON-object response mode for the gpt-4-turbo /
        # gpt-4o families. Older models ignore the field harmlessly.
        payload["response_format"] = {"type": "json_object"}
    response = await client.post(url, json=payload, headers=headers)
    response.raise_for_status()
    body = response.json()
    return body["choices"][0]["message"]["content"]


# ---------------------------------------------------------------------------
# Public manager
# ---------------------------------------------------------------------------


class LLMManager:
    """Thin async adapter for healthcare-grade LLM endpoints.

    Single instance per ``Agent``. Holds no per-request state so it's
    safe to share across concurrent requests; each call opens its own
    ``httpx.AsyncClient`` so a slow provider can't poison a shared pool.
    """

    def __init__(self, memory=None, timeout: float = 30.0):
        self.memory = memory
        self._timeout = timeout
        self._provider = _resolve_provider()
        self._model = _resolve_model_for_provider(self._provider)

    # ------------------------------------------------------------------
    # Internal: retry-aware dispatch
    # ------------------------------------------------------------------

    async def _call_provider(self, prompt: str, *, structured: bool) -> str:
        """Dispatch to the configured provider with one-shot 429/503 retry."""

        provider = self._provider
        if provider == "anthropic" and not _anthropic_api_key():
            logger.warning(
                "LLM_PROVIDER=anthropic but ANTHROPIC_API_KEY is missing; "
                "falling back to OpenAI for this call. Set ANTHROPIC_API_KEY "
                "to honour the manual's primary-provider directive."
            )
            provider = "openai"

        if provider == "openai" and not _openai_api_key():
            raise RetryError(
                "No usable LLM provider: neither ANTHROPIC_API_KEY nor "
                "OPENAI_API_KEY/LLM_API_KEY is set."
            )

        last_error: Optional[Exception] = None
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            for attempt in range(2):
                try:
                    if provider == "anthropic":
                        return await _anthropic_chat(
                            client,
                            api_key=_anthropic_api_key(),
                            model=self._model,
                            prompt=prompt,
                            structured=structured,
                        )
                    return await _openai_chat(
                        client,
                        api_key=_openai_api_key(),
                        model=self._model,
                        prompt=prompt,
                        structured=structured,
                    )
                except httpx.HTTPStatusError as e:
                    if e.response.status_code not in {429, 503}:
                        raise
                    last_error = e
                    if attempt == 0:
                        await asyncio.sleep(1.0)
                        continue
                    raise RetryError(
                        f"{provider} provider returned {e.response.status_code} after retry"
                    ) from e
        raise RetryError("LLM provider retry exhausted") from last_error

    # ------------------------------------------------------------------
    # Public async surface
    # ------------------------------------------------------------------

    async def ask_llm_async(self, prompt: str) -> str:
        """Free-text completion. Returns "Error: ..." strings on failure for
        backward compatibility with ``core/agent.py``'s string handling."""

        try:
            _baa_guard(prompt)
        except BAAGuardError as e:
            logger.error("BAA guard blocked free-text LLM call: %s", e)
            return f"Refused by BAA guard: {e}"

        try:
            return await self._call_provider(prompt, structured=False)
        except Exception as e:
            logger.warning("LLM provider call failed: %s", e)
            return f"Clinical LLM Connection Error: {str(e)}"

    async def ask_llm_structured_async(self, prompt: str, schema) -> Any:
        """Structured output. Returns a parsed ``schema`` instance.

        Adds the schema to the prompt so the model knows the target shape,
        then defensively extracts the first JSON object from the response
        before validating with pydantic. Mirrors the previous LangChain-
        coupled behaviour without the dependency.
        """

        _baa_guard(prompt)

        try:
            schema_hint = schema.model_json_schema()
        except Exception:
            schema_hint = {"type": "object"}
        prompt_with_schema = (
            f"{prompt}\n\nCRITICAL: Return a valid JSON object EXACTLY adhering to "
            f"this schema:\n{json.dumps(schema_hint)}"
        )
        raw = await self._call_provider(prompt_with_schema, structured=True)
        candidate = _extract_json_object(raw)
        try:
            return schema.model_validate_json(candidate)
        except Exception as e:
            raise RuntimeError(f"Structured Parsing Error: {e}") from e

    # ------------------------------------------------------------------
    # Sync wrappers (for the synchronous Agent layer)
    # ------------------------------------------------------------------

    def _run(self, coro):
        """Run an async coroutine from a sync context.

        Uses a dedicated worker thread when there's already a running
        event loop (FastAPI handlers) so we don't crash with
        ``RuntimeError: cannot run loop while another is running``.
        """

        try:
            asyncio.get_running_loop()
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(asyncio.run, coro).result()
        except RuntimeError:
            return asyncio.run(coro)

    def ask_llm(self, prompt: str) -> str:
        return self._run(self.ask_llm_async(prompt))

    def ask_llm_structured(self, prompt: str, schema) -> Any:
        return self._run(self.ask_llm_structured_async(prompt, schema))

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    @property
    def provider(self) -> str:
        return self._provider

    @property
    def model(self) -> str:
        return self._model


__all__ = [
    "BAAGuardError",
    "LLMManager",
    "RetryError",
]
