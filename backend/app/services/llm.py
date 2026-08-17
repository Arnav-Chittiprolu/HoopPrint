"""LLM provider abstraction. Gemini narrates Phase 6 why + rec JSON only."""

from __future__ import annotations

from typing import Protocol

import certifi
import httpx

from app.config import Settings


class LLMProvider(Protocol):
    async def generate(self, prompt: str) -> str: ...


class GeminiProvider:
    def __init__(
        self,
        api_key: str,
        *,
        model: str = "gemini-2.5-flash",
        timeout: float = 25.0,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    async def generate(self, prompt: str) -> str:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent"
        )
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 900},
        }
        async with httpx.AsyncClient(timeout=self.timeout, verify=certifi.where()) as client:
            response = await client.post(url, params={"key": self.api_key}, json=payload)
        if response.status_code >= 400:
            raise RuntimeError(f"Gemini error {response.status_code}: {response.text[:400]}")
        data = response.json()
        candidates = data.get("candidates") or []
        if not candidates:
            return ""
        parts = ((candidates[0].get("content") or {}).get("parts")) or []
        texts = [p.get("text", "") for p in parts if isinstance(p, dict)]
        return "".join(texts).strip()


class AnthropicProvider:
    """Stub — set LLM_PROVIDER=anthropic later without changing the pipeline."""

    async def generate(self, prompt: str) -> str:
        raise NotImplementedError("Anthropic provider is not wired yet")


class OpenAIProvider:
    """Stub — set LLM_PROVIDER=openai later without changing the pipeline."""

    async def generate(self, prompt: str) -> str:
        raise NotImplementedError("OpenAI provider is not wired yet")


def get_llm_provider(settings: Settings) -> LLMProvider | None:
    provider = (settings.llm_provider or "gemini").strip().lower()
    if provider in {"", "none", "off"}:
        return None
    if provider == "gemini":
        key = (settings.gemini_api_key or "").strip()
        if not key:
            return None
        return GeminiProvider(key, model=settings.gemini_model)
    if provider == "anthropic":
        return AnthropicProvider()
    if provider == "openai":
        return OpenAIProvider()
    return None
