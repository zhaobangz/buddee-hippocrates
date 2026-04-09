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

    _local_pipeline = None

    @classmethod
    def get_pipeline(cls):
        if cls._local_pipeline is None:
            if transformers is None:
                return None
            
            device_str, device_index = get_torch_device(Config.PREFERRED_DEVICE, Config.FORCE_CPU)
            try:
                # Use FP16 for efficiency on MPS/CUDA
                kwargs = {}
                if torch is not None and device_str in ('mps', 'cuda'):
                    kwargs["torch_dtype"] = torch.float16
                
                # device_index 0 for CUDA, -1 for CPU/MPS (MPS is usually -1 in pipeline + device_map)
                # But for MPS, device_map="auto" is often better
                cls._local_pipeline = transformers.pipeline(
                    'text-generation', 
                    model=Config.LLM_MODEL, 
                    device_map="auto" if device_str != 'cpu' else None,
                    **kwargs
                )
            except Exception:
                # Fallback to standard loading if device_map fails
                cls._local_pipeline = transformers.pipeline(
                    'text-generation', 
                    model=Config.LLM_MODEL, 
                    device=device_index
                )
        return cls._local_pipeline

    def ask_llm(self, user_input: str, timeout: Optional[int] = 15) -> str:
        """Send a chat request to the configured LLM provider and return text.

        This implementation is generic and expects a DeepSeek-like API but can
        be adapted by changing `Config` values.
        """
        # If configured to use a local model, try to run locally (and prefer GPU)
        if Config.LLM_PROVIDER and Config.LLM_PROVIDER.lower() == 'local':
            pipe = self.get_pipeline()
            if pipe is None:
                return "Local model requested but the 'transformers' package is not installed."

            try:
                messages = self._build_messages(user_input)
                # Use MedGemma chat template if available
                out = pipe(messages, max_new_tokens=512, do_sample=False)
                
                if isinstance(out, list) and out:
                    # Logic for chat-based output
                    gen = out[0].get('generated_text')
                    if isinstance(gen, list) and len(gen) > 0:
                         return gen[-1].get('content', str(gen[-1]))
                    return str(gen)
                return str(out)
            except Exception as e:
                # Fall back to remote API if configured
                if not self.api_key or not self.api_url:
                    return f"Failed to run local model: {e}"

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

