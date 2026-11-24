from app.models import AffiliateLink, ChatSession, Click
from app.providers import flights
from tests.conftest import DEVICE, SAMPLE_FLIGHTS, text, tool_call


async def _record(seen, kw):
    seen.update(kw)
    return SAMPLE_FLIGHTS


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_chat_requires_device_id(client):
    assert client.post("/api/chat", json={"message": "hi"}).status_code == 400


def test_chat_without_ai_key_returns_503(client):
    r = client.post("/api/chat", json={"message": "hi"}, headers=DEVICE)
    assert r.status_code == 503
    assert "ANTHROPIC_API_KEY" in r.json()["detail"]


def test_flight_only_request_returns_tracked_cards(client, db, use_llm, monkeypatch):
    seen = {}
    monkeypatch.setattr(flights, "search_flights", lambda **kw: _record(seen, kw))
    llm = use_llm([
        tool_call("search_flights", {"origin": "PER", "destination": "SYD", "departure_date": "2026-11-27"}),
        text("Jetstar's direct 6am flight is the best value."),
    ])

    r = client.post("/api/chat", json={"message": "Cheapest flight Perth to Sydney Friday"}, headers=DEVICE)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["reply"].startswith("Jetstar")
    assert seen["origin"] == "PER"

    (card,) = body["cards"]
    assert card["type"] == "flights"
    assert card["title"] == "PER → SYD"
    links = [f["booking_link"] for f in card["results"]]
    assert all(link.startswith("http://testserver/go/") for link in links)
    assert all("url" not in f for f in card["results"])  # raw partner URL is never exposed

    # The model got the tool result back, paired with its tool_use id.
    tool_result = llm.calls[1]["messages"][-1]["content"][0]
    assert tool_result["type"] == "tool_result" and tool_result["tool_use_id"] == "tu_1"

    # Conversation is saved and links are stored.
    session = db.get(ChatSession, body["session_id"])
    assert session.device_id == DEVICE["X-Device-Id"]
    assert [m["role"] for m in session.history] == ["user", "assistant", "user", "assistant"]
    assert db.query(AffiliateLink).count() == 2

    # Clicking Book records a click and redirects to the partner with our marker.
    link_id = links[0].rsplit("/", 1)[1]
    go = client.get(f"/go/{link_id}", follow_redirects=False)
    assert go.status_code == 302
    assert go.headers["location"] == SAMPLE_FLIGHTS["results"][0]["url"]
    assert db.query(Click).filter_by(link_id=link_id).count() == 1


def test_follow_up_continues_session(client, use_llm, monkeypatch):
    llm = use_llm([text("Where are you flying from?"), text("Got it, from Perth.")])
    first = client.post("/api/chat", json={"message": "Flight to Sydney Friday"}, headers=DEVICE).json()
    second = client.post(
        "/api/chat", json={"message": "From Perth", "session_id": first["session_id"]}, headers=DEVICE
    ).json()
    assert second["session_id"] == first["session_id"]
    sent = llm.calls[1]["messages"]
    assert [m["content"] for m in sent if m["role"] == "user"] == ["Flight to Sydney Friday", "From Perth"]


def test_other_device_cannot_reuse_session(client, use_llm):
    use_llm([text("Hi"), text("Hi again")])
    first = client.post("/api/chat", json={"message": "hello"}, headers=DEVICE).json()
    other = client.post(
        "/api/chat", json={"message": "hello", "session_id": first["session_id"]},
        headers={"X-Device-Id": "device-intruder1"},
    ).json()
    assert other["session_id"] != first["session_id"]


def test_hotel_only_request_gives_tracked_search_link(client, use_llm):
    use_llm([
        tool_call("search_hotels", {"city": "Perth", "near": "Perth Airport", "check_in": "2026-11-24", "check_out": "2026-11-25"}),
        text("Here are hotels near the airport for tonight."),
    ])
    body = client.post("/api/chat", json={"message": "Hotel near Perth airport tonight"}, headers=DEVICE).json()
    (card,) = body["cards"]
    assert card["type"] == "hotels" and card["title"] == "Hotels near Perth Airport, Perth"
    go = client.get(card["search_link"].replace("http://testserver", ""), follow_redirects=False)
    assert go.status_code == 302
    assert "booking.com" in go.headers["location"] and "aid=999" in go.headers["location"]


def test_extras_and_missing_partner(client, use_llm):
    use_llm([tool_call("get_extra_links", {"categories": ["esim", "insurance"]}), text("Here you go.")])
    body = client.post("/api/chat", json={"message": "eSIM and insurance for Bali"}, headers=DEVICE).json()
    (card,) = body["cards"]
    assert [x["category"] for x in card["results"]] == ["esim"]  # insurance link not configured


def test_tool_errors_go_back_to_the_model(client, use_llm, monkeypatch):
    async def broken(**kw):
        raise RuntimeError("boom")
    monkeypatch.setattr(flights, "search_flights", broken)
    llm = use_llm([
        tool_call("search_flights", {"origin": "PER", "destination": "SYD", "departure_date": "2026-11-27"}),
        text("Flight search is having trouble right now."),
    ])
    r = client.post("/api/chat", json={"message": "flight"}, headers=DEVICE)
    assert r.status_code == 200
    result = llm.calls[1]["messages"][-1]["content"][0]
    assert result["is_error"] is True and "failed" in result["content"]


def test_unknown_link_404(client):
    assert client.get("/go/nope", follow_redirects=False).status_code == 404
