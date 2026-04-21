"""
Buddi LLM Manager — Async v4 (ARCH-02)

Uses ``httpx.AsyncClient`` so that clinical LLM calls do not block the
FastAPI event loop. Sync wrappers are retained for legacy callers that
still invoke ``ask_llm`` from non-async contexts (agent orchestrator).
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from core.config import Config


class LLMManager:
    """Thin async adapter for healthcare-grade LLM endpoints."""

    def __init__(self, memory=None, timeout: float = 15.0):
        self.memory = memory
        self._timeout = timeout

    # ------------------------------------------------------------------
    # Async primitives
    # ------------------------------------------------------------------
    async def ask_llm_async(self, prompt: str) -> str:
        if not Config.LLM_API_KEY:
            return "Error: LLM API Key not configured."

        headers = {"Authorization": f"Bearer {Config.LLM_API_KEY}"}
        payload = {
            "model": Config.LLM_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                r = await client.post(Config.LLM_API_URL, json=payload, headers=headers)
                r.raise_for_status()
                return r.json()["choices"][0]["message"]["content"]
        except Exception as e:
            return f"Clinical LLM Connection Error: {str(e)}"

    async def ask_llm_structured_async(self, prompt: str, schema) -> Any:
        if not Config.LLM_API_KEY:
            raise ValueError("Error: LLM API Key not configured.")

        headers = {"Authorization": f"Bearer {Config.LLM_API_KEY}"}
        prompt_with_schema = (
            prompt
            + "\n\nCRITICAL: Return a valid JSON object EXACTLY adhering to "
            f"this schema:\n{schema.model_json_schema()}"
        )
        payload = {
            "model": Config.LLM_MODEL,
            "messages": [{"role": "user", "content": prompt_with_schema}],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                r = await client.post(Config.LLM_API_URL, json=payload, headers=headers)
                r.raise_for_status()
                content = r.json()["choices"][0]["message"]["content"]
                return schema.model_validate_json(content)
        except Exception as e:
            raise RuntimeError(f"Structured Parsing Error: {str(e)}")

    # ------------------------------------------------------------------
    # Sync wrappers (for the synchronous Agent layer)
    # ------------------------------------------------------------------
    def _run(self, coro):
        """Run an async coroutine from a sync context.

        Uses a dedicated new event loop to avoid clashing with an already
        running loop (e.g. inside FastAPI handlers — those should call the
        async methods directly).
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Schedule into a fresh loop in a worker thread so we don't
                # re-enter the running one.
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    return pool.submit(asyncio.run, coro).result()
        except RuntimeError:
            pass
        return asyncio.run(coro)

    def ask_llm(self, prompt: str) -> str:
        return self._run(self.ask_llm_async(prompt))

    def ask_llm_structured(self, prompt: str, schema) -> Any:
        return self._run(self.ask_llm_structured_async(prompt, schema))
