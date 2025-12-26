"""LLM manager: small adapter for external LLMs.

This module provides a minimal `LLMManager` that sends a chat-style request
to a configured LLM provider. It is intentionally simple so it can be
replaced/extended for other providers.
"""

import requests
from typing import Optional
from core.config import Config

from core.device import get_torch_device

try:
    import transformers
except Exception:
    transformers = None

try:
    import torch
except Exception:
    torch = None


class LLMManager:
    def __init__(self, memory=None):
        self.memory = memory
        self.api_url = Config.LLM_API_URL
        self.api_key = Config.LLM_API_KEY
        self.model = Config.LLM_MODEL

    def _build_messages(self, user_input: str) -> list:
        messages = []
        # include recent memory if available
        try:
            if self.memory:
                history = self.memory.recall()
                for item in history:
                    # memory stores dicts with 'user' and 'assistant' or similar
                    u = item.get('user') or item.get('prompt')
                    a = item.get('assistant') or item.get('response')
                    if u:
                        messages.append({'role': 'user', 'content': u})
                    if a:
                        messages.append({'role': 'assistant', 'content': a})
        except Exception:
            pass

        messages.append({'role': 'user', 'content': user_input})
        return messages

    def ask_llm(self, user_input: str, timeout: Optional[int] = 15) -> str:
        """Send a chat request to the configured LLM provider and return text.

        This implementation is generic and expects a DeepSeek-like API but can
        be adapted by changing `Config` values.
        """
        # If configured to use a local model, try to run locally (and prefer GPU)
        if Config.LLM_PROVIDER and Config.LLM_PROVIDER.lower() == 'local':
            # require transformers to be installed
            if transformers is None:
                return "Local model requested but the 'transformers' package is not installed."

            # Try to load a local model and run on preferred device
            device_str, device_index = get_torch_device(Config.PREFERRED_DEVICE, Config.FORCE_CPU)
            try:
                # use pipeline for text-generation if available
                pipe = transformers.pipeline('text-generation', model=self.model, device=device_index)
                out = pipe(user_input, max_length=512, do_sample=False)
                if isinstance(out, list) and out:
                    return out[0].get('generated_text', str(out[0]))
                return str(out)
            except Exception as e:
                # Fall back to remote API if configured
                if not self.api_key or not self.api_url:
                    return f"Failed to run local model on device {device_str}: {e}"
                # otherwise continue to try remote provider

        if not self.api_key or not self.api_url:
            return "LLM is not configured (missing API key or URL)."

        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
        }

        payload = {
            'model': self.model,
            'messages': self._build_messages(user_input),
            'temperature': 0.7,
            'max_tokens': 512,
        }

        try:
            resp = requests.post(self.api_url, headers=headers, json=payload, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            # Expecting DeepSeek/OpenAI style response
            for key in ("choices",):
                if key in data and data[key]:
                    msg = data[key][0].get('message') or data[key][0]
                    if isinstance(msg, dict):
                        return msg.get('content', '')
                    return str(msg)
            # Fallback: try 'text' or top-level string
            if isinstance(data, dict) and 'text' in data:
                return data['text']
            return str(data)
        except Exception as e:
            return f"Error contacting LLM: {e}"


__all__ = ['LLMManager']

