import asyncio

from app.agent.agent import FALLBACK_REPLY, MAX_TOOL_ROUNDS, run_agent, trim_history
from app.agent.tools import ToolContext, run_tool
from app.config import settings
from app.routers import telegram
from tests.conftest import DEVICE, FakeLLM, text, tool_call


def test_trim_history_never_splits_tool_pairs():
    history = []
    for i in range(20):
        history += [
            {"role": "user", "content": f"q{i}"},
            {"role": "assistant", "content": [{"type": "tool_use", "id": f"t{i}", "name": "x", "input": {}}]},
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": f"t{i}", "content": "{}"}]},
            {"role": "assistant", "content": [{"type": "text", "text": "a"}]},
        ]
    trimmed = trim_history(history, max_user_turns=5)
    assert trimmed[0] == {"role": "user", "content": "q15"}
    assert len(trimmed) == 20


def test_agent_stops_after_max_rounds(db):
    llm = FakeLLM([tool_call("resolve_place", {"name": "x"}, f"t{i}") for i in range(MAX_TOOL_ROUNDS)])

    async def go():
        ctx = ToolContext(db=db, device_id="d")
        return await run_agent(llm, [{"role": "user", "content": "loop"}], ctx)

    import app.agent.tools as tools

    async def fake_place(name, locale="en"):
        return {"found": False}

    tools.places.resolve_place, original = fake_place, tools.places.resolve_place
    try:
        result = asyncio.run(go())
    finally:
        tools.places.resolve_place = original
    assert result.reply == FALLBACK_REPLY
    assert result.history[-1]["role"] == "assistant"  # history stays valid for the next turn


def test_unknown_tool_and_bad_args(db):
    ctx = ToolContext(db=db, device_id="d")
    assert "Unknown tool" in asyncio.run(run_tool("nope", {}, ctx))["error"]
    assert "Invalid arguments" in asyncio.run(run_tool("resolve_place", {"bogus": 1}, ctx))["error"]


def test_admin_stats_requires_token(client, use_llm):
    assert client.get("/api/admin/stats").status_code == 401
    assert client.get("/api/admin/stats", headers={"Authorization": "Bearer wrong"}).status_code == 401

    use_llm([tool_call("get_extra_links", {"categories": ["esim"]}), text("ok")])
    card = client.post("/api/chat", json={"message": "esim"}, headers=DEVICE).json()["cards"][0]
    client.get(card["results"][0]["link"].replace("http://testserver", ""), follow_redirects=False)

    stats = client.get("/api/admin/stats", headers={"Authorization": "Bearer admin-secret"}).json()
    assert stats["chat_sessions"] == 1
    assert stats["by_category"] == [{"category": "esim", "links_shown": 1, "clicks": 1, "click_rate": 1.0}]


def test_telegram_webhook(client, use_llm, monkeypatch):
    sent = []

    async def fake_send(chat_id, msg):
        sent.append((chat_id, msg))

    monkeypatch.setattr(telegram, "send_message", fake_send)
    monkeypatch.setattr(settings, "telegram_bot_token", "bot-token")
    monkeypatch.setattr(settings, "telegram_webhook_secret", "s3cret")

    update = {"message": {"chat": {"id": 42}, "text": "eSIM for Bali"}}
    assert client.post("/api/telegram/webhook", json=update).status_code == 401

    use_llm([tool_call("get_extra_links", {"categories": ["esim"]}), text("Here's an eSIM option.")])
    headers = {"X-Telegram-Bot-Api-Secret-Token": "s3cret"}
    assert client.post("/api/telegram/webhook", json=update, headers=headers).status_code == 200
    chat_id, msg = sent[-1]
    assert chat_id == 42
    assert "Here's an eSIM option." in msg and "http://testserver/go/" in msg and "commission" in msg


def test_telegram_disabled_by_default(client):
    assert client.post("/api/telegram/webhook", json={}).status_code == 404
