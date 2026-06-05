"""Provider-agnostic tool-use loop for the college subagent.

The subagent describes its tools + system prompt once; this module runs the agentic
loop against whichever LLM provider is configured (LLM_PROVIDER): `openai` (default) or
`anthropic`. Tools are given in a neutral shape — {name, description, input_schema} — and
adapted to each provider's function/tool-calling format. Returns the `report` tool's
arguments (the structured findings) or None if the agent never reported.
"""
from __future__ import annotations

import json
import os
from typing import Awaitable, Callable

import structlog

from app.llm import llm_provider  # single source of the provider switch

log = structlog.get_logger()

ToolExecutor = Callable[[str, dict], Awaitable[str]]


async def run_subagent_loop(
    system: str,
    user_text: str,
    tools: list[dict],
    execute_tool: ToolExecutor,
    *,
    max_rounds: int,
    final_tool: str,
) -> dict | None:
    provider = llm_provider()
    try:
        if provider == "anthropic":
            return await _anthropic_loop(system, user_text, tools, execute_tool, max_rounds, final_tool)
        return await _openai_loop(system, user_text, tools, execute_tool, max_rounds, final_tool)
    except Exception as exc:  # noqa: BLE001
        log.warning("subagent_llm_error", provider=provider, error=str(exc))
        return None


# ── OpenAI (function calling) ───────────────────────────────────────────────────

async def _openai_loop(system, user_text, tools, execute_tool, max_rounds, final_tool) -> dict | None:
    from openai import AsyncOpenAI

    client = AsyncOpenAI()
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    oai_tools = [
        {"type": "function", "function": {
            "name": t["name"], "description": t["description"], "parameters": t["input_schema"],
        }}
        for t in tools
    ]
    messages: list[dict] = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_text},
    ]
    for round_no in range(max_rounds):
        force = round_no == max_rounds - 1
        resp = await client.chat.completions.create(
            model=model, messages=messages, tools=oai_tools,
            tool_choice={"type": "function", "function": {"name": final_tool}} if force else "auto",
        )
        msg = resp.choices[0].message
        if not msg.tool_calls:
            break
        messages.append({
            "role": "assistant",
            "content": msg.content or "",
            "tool_calls": [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in msg.tool_calls
            ],
        })
        report = None
        for tc in msg.tool_calls:
            args = _parse_args(tc.function.arguments)
            if tc.function.name == final_tool:
                report = args
            out = await execute_tool(tc.function.name, args)
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": out})
        if report is not None:
            return report
    return None


# ── Anthropic (tool use) ────────────────────────────────────────────────────────

async def _anthropic_loop(system, user_text, tools, execute_tool, max_rounds, final_tool) -> dict | None:
    import anthropic

    client = anthropic.AsyncAnthropic()
    model = os.getenv("AGENT_MODEL", os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6"))
    timeout = float(os.getenv("CLAUDE_TIMEOUT_S", "30"))
    messages: list[dict] = [{"role": "user", "content": user_text}]
    for round_no in range(max_rounds):
        force = round_no == max_rounds - 1
        resp = await client.messages.create(
            model=model, max_tokens=1500, system=system, tools=tools,
            tool_choice={"type": "tool", "name": final_tool} if force else {"type": "auto"},
            messages=messages, timeout=timeout,
        )
        tool_uses = [b for b in resp.content if getattr(b, "type", None) == "tool_use"]
        if not tool_uses:
            break
        messages.append({"role": "assistant", "content": resp.content})
        report = None
        results = []
        for tu in tool_uses:
            if tu.name == final_tool:
                report = dict(tu.input)
            out = await execute_tool(tu.name, dict(tu.input))
            results.append({"type": "tool_result", "tool_use_id": tu.id, "content": out})
        messages.append({"role": "user", "content": results})
        if report is not None:
            return report
    return None


def _parse_args(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}
