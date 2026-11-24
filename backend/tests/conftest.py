import os

# Configure before the app is imported.
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["TRAVELPAYOUTS_TOKEN"] = "test-token"
os.environ["TRAVELPAYOUTS_MARKER"] = "12345"
os.environ["BOOKING_AID"] = "999"
os.environ["ADMIN_TOKEN"] = "admin-secret"
os.environ["PUBLIC_BASE_URL"] = "http://testserver"
os.environ["ESIM_AFFILIATE_URL"] = "https://esim.example/?ref=me"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.agent.llm import LLMResponse  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.deps import llm_client, optional_llm_client  # noqa: E402
from app.main import app  # noqa: E402

DEVICE = {"X-Device-Id": "device-aaaaaaaa"}
OTHER_DEVICE = {"X-Device-Id": "device-bbbbbbbb"}

SAMPLE_FLIGHTS = {
    "type": "flights",
    "origin": "PER",
    "destination": "SYD",
    "price_note": "Recent fares.",
    "results": [
        {"airline": "JQ", "flight_number": "975", "from": "PER", "to": "SYD", "departure_at": "2026-11-27T06:00:00+08:00",
         "return_at": None, "stops": 0, "duration_minutes": 270, "price": 189, "currency": "AUD",
         "url": "https://www.aviasales.com/search/PER2711SYD1?marker=12345"},
        {"airline": "VA", "flight_number": "566", "from": "PER", "to": "SYD", "departure_at": "2026-11-27T09:00:00+08:00",
         "return_at": None, "stops": 0, "duration_minutes": 265, "price": 229, "currency": "AUD",
         "url": "https://www.aviasales.com/search/PER2711SYD1?marker=12345&x=2"},
    ],
}


class FakeLLM:
    """Plays back scripted responses and records what it was sent."""

    def __init__(self, responses: list[LLMResponse]):
        self.responses = list(responses)
        self.calls: list[dict] = []

    async def complete(self, system, messages, tools):
        self.calls.append({"system": system, "messages": [dict(m) for m in messages], "tools": tools})
        return self.responses.pop(0)


def tool_call(name: str, args: dict, call_id: str = "tu_1") -> LLMResponse:
    return LLMResponse("tool_use", [{"type": "tool_use", "id": call_id, "name": name, "input": args}])


def text(reply: str) -> LLMResponse:
    return LLMResponse("end_turn", [{"type": "text", "text": reply}])


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def db():
    with SessionLocal() as s:
        yield s


@pytest.fixture
def use_llm():
    def _use(responses):
        fake = FakeLLM(responses)
        app.dependency_overrides[llm_client] = lambda: fake
        app.dependency_overrides[optional_llm_client] = lambda: fake
        return fake
    return _use
