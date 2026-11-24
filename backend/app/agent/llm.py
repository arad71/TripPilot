"""Thin LLM wrapper, so the agent loop doesn't depend on one vendor's SDK.

Messages use the Anthropic format (role + content blocks). To use another provider,
write a class with the same `complete()` method and return it from `get_llm()`.
"""
from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol

from app.config import settings


class LLMNotConfigured(Exception):
    pass


class LLMError(Exception):
    pass


@dataclass
class LLMResponse:
    stop_reason: str  # "tool_use" when the model wants tools run, else "end_turn" etc.
    content: list[dict]  # [{"type": "text", "text": ...} | {"type": "tool_use", "id", "name", "input"}]


class LLMClient(Protocol):
    async def complete(self, system: str, messages: list[dict], tools: list[dict]) -> LLMResponse: ...


class AnthropicLLM:
    def __init__(self, api_key: str, model: str, max_tokens: int = 1500):
        from anthropic import AsyncAnthropic

        self.client = AsyncAnthropic(api_key=api_key)
        self.model = model
        self.max_tokens = max_tokens

    async def complete(self, system: str, messages: list[dict], tools: list[dict]) -> LLMResponse:
        import anthropic

        try:
            r = await self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=system,
                tools=tools,
                messages=messages,
            )
        except anthropic.APIError as e:
            raise LLMError(str(e)) from e

        blocks: list[dict] = []
        for b in r.content:
            if b.type == "text":
                blocks.append({"type": "text", "text": b.text})
            elif b.type == "tool_use":
                blocks.append({"type": "tool_use", "id": b.id, "name": b.name, "input": b.input})
        return LLMResponse(stop_reason=r.stop_reason or "end_turn", content=blocks)


@lru_cache
def _anthropic(api_key: str, model: str) -> AnthropicLLM:
    return AnthropicLLM(api_key, model)


def get_llm() -> LLMClient:
    if not settings.anthropic_api_key:
        raise LLMNotConfigured("The AI assistant is not set up yet (ANTHROPIC_API_KEY missing).")
    return _anthropic(settings.anthropic_api_key, settings.llm_model)
