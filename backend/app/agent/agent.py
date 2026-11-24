"""The agent loop: send the conversation to the LLM, run any tools it asks for, repeat."""
import json
from dataclasses import dataclass
from datetime import date

from app.agent.llm import LLMClient
from app.agent.prompts import SYSTEM_PROMPT
from app.agent.tools import TOOLS, ToolContext, run_tool
from app.config import settings

MAX_TOOL_ROUNDS = 6
MAX_USER_TURNS = 12
MAX_TOOL_RESULT_CHARS = 15000
FALLBACK_REPLY = "Sorry, I couldn't finish that. Could you rephrase or narrow it down?"


@dataclass
class AgentResult:
    reply: str
    cards: list[dict]
    history: list[dict]


def trim_history(history: list[dict], max_user_turns: int = MAX_USER_TURNS) -> list[dict]:
    """Keep the last N user turns. Cuts only at a typed user message, so a tool_use is never
    separated from its tool_result."""
    starts = [i for i, m in enumerate(history) if m["role"] == "user" and isinstance(m["content"], str)]
    if len(starts) <= max_user_turns:
        return history
    return history[starts[-max_user_turns]:]


async def run_agent(llm: LLMClient, history: list[dict], ctx: ToolContext, today: date | None = None) -> AgentResult:
    """`history` must end with the new user message."""
    system = SYSTEM_PROMPT.format(
        today=(today or date.today()).isoformat(), currency=settings.default_currency.upper()
    )
    history = trim_history(list(history))

    for _ in range(MAX_TOOL_ROUNDS):
        resp = await llm.complete(system=system, messages=history, tools=TOOLS)
        history.append({"role": "assistant", "content": resp.content})

        if resp.stop_reason != "tool_use":
            text = "\n".join(b["text"] for b in resp.content if b.get("type") == "text").strip()
            return AgentResult(text or FALLBACK_REPLY, ctx.cards, history)

        results = []
        for block in resp.content:
            if block.get("type") != "tool_use":
                continue
            out = await run_tool(block["name"], block.get("input") or {}, ctx)
            result = {
                "type": "tool_result",
                "tool_use_id": block["id"],
                "content": json.dumps(out, default=str)[:MAX_TOOL_RESULT_CHARS],
            }
            if "error" in out:
                result["is_error"] = True
            results.append(result)
        history.append({"role": "user", "content": results})

    # Too many rounds: close the turn with an assistant message so history stays valid.
    history.append({"role": "assistant", "content": [{"type": "text", "text": FALLBACK_REPLY}]})
    return AgentResult(FALLBACK_REPLY, ctx.cards, history)
