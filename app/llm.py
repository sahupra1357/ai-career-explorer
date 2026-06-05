"""Provider-agnostic LLM text completion.

One switch — LLM_PROVIDER (openai default, anthropic switchable) — for all the text/JSON/
chat features: compare summary, deep-dive, explore chat, and page extraction. The agentic
tool-use loop has its own provider switch in course_search/agent_llm.py; both read
LLM_PROVIDER, so flipping it moves the whole app between providers.
"""
from __future__ import annotations

import os

import structlog

log = structlog.get_logger()


def llm_provider() -> str:
    return (os.getenv("LLM_PROVIDER") or "openai").strip().lower()


def mock_llm() -> bool:
    """Honor both the provider-neutral MOCK_LLM and the legacy MOCK_CLAUDE."""
    return os.getenv("MOCK_LLM") == "1" or os.getenv("MOCK_CLAUDE") == "1"


async def complete(messages: list[dict] | str, *, system: str | None = None, max_tokens: int = 1024) -> str | None:
    """Return the model's text reply, or None on failure. `messages` may be a bare prompt."""
    if mock_llm():
        return "[MOCK LLM] response — unset MOCK_LLM / MOCK_CLAUDE for real output."
    if isinstance(messages, str):
        messages = [{"role": "user", "content": messages}]
    provider = llm_provider()
    try:
        if provider == "anthropic":
            return await _anthropic(messages, system, max_tokens)
        return await _openai(messages, system, max_tokens)
    except Exception as exc:  # noqa: BLE001
        log.error("llm_error", provider=provider, error=str(exc))
        return None


async def _openai(messages: list[dict], system: str | None, max_tokens: int) -> str | None:
    from openai import AsyncOpenAI

    client = AsyncOpenAI()
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    msgs = ([{"role": "system", "content": system}] if system else []) + messages
    resp = await client.chat.completions.create(model=model, messages=msgs, max_tokens=max_tokens)
    return (resp.choices[0].message.content or "").strip() or None


async def _anthropic(messages: list[dict], system: str | None, max_tokens: int) -> str | None:
    import anthropic

    client = anthropic.AsyncAnthropic()
    model = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
    kwargs: dict = {"model": model, "max_tokens": max_tokens, "messages": messages}
    if system:
        kwargs["system"] = system
    msg = await client.messages.create(**kwargs)
    return msg.content[0].text.strip()
