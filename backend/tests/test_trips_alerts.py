import asyncio

from app.jobs.price_alerts import check_alerts
from app.models import PriceAlert
from tests.conftest import DEVICE, OTHER_DEVICE, SAMPLE_FLIGHTS, text, tool_call

ITEM = {"kind": "flight", "title": "PER → SYD · JQ", "price": 189, "currency": "AUD", "link": "http://testserver/go/x"}


def test_quick_save_creates_default_trip(client):
    r = client.post("/api/trips/quick-save", json=ITEM, headers=DEVICE)
    assert r.status_code == 201
    trip = r.json()
    assert trip["name"] == "My trips" and len(trip["items"]) == 1

    client.post("/api/trips/quick-save", json={**ITEM, "kind": "hotel", "title": "Hotel"}, headers=DEVICE)
    trips = client.get("/api/trips", headers=DEVICE).json()
    assert len(trips) == 1 and len(trips[0]["items"]) == 2


def test_trip_items_are_private_to_device(client):
    item_id = client.post("/api/trips/quick-save", json=ITEM, headers=DEVICE).json()["items"][0]["id"]
    assert client.get("/api/trips", headers=OTHER_DEVICE).json() == []
    assert client.patch(f"/api/trips/items/{item_id}", json={"status": "booked"}, headers=OTHER_DEVICE).status_code == 404
    assert client.delete(f"/api/trips/items/{item_id}", headers=OTHER_DEVICE).status_code == 404

    r = client.patch(f"/api/trips/items/{item_id}", json={"status": "booked"}, headers=DEVICE)
    assert r.json()["status"] == "booked"
    assert client.delete(f"/api/trips/items/{item_id}", headers=DEVICE).status_code == 204


def test_alert_validation(client):
    bad = {"origin": "Perth", "destination": "SYD", "depart_month": "2026-12", "target_price": 200}
    assert client.post("/api/alerts", json=bad, headers=DEVICE).status_code == 422


def test_alert_crud(client):
    body = {"origin": "per", "destination": "dps", "depart_month": "2027-03", "return_month": "2027-03", "target_price": 350}
    created = client.post("/api/alerts", json=body, headers=DEVICE).json()
    assert created["origin"] == "PER" and created["currency"] == "AUD"
    assert len(client.get("/api/alerts", headers=DEVICE).json()) == 1
    assert client.get("/api/alerts", headers=OTHER_DEVICE).json() == []
    assert client.delete(f"/api/alerts/{created['id']}", headers=OTHER_DEVICE).status_code == 404
    assert client.delete(f"/api/alerts/{created['id']}", headers=DEVICE).status_code == 204


def test_agent_can_create_alert(client, db, use_llm):
    use_llm([
        tool_call("create_price_alert", {"origin": "PER", "destination": "DPS", "depart_month": "2027-03", "target_price": 300}),
        text("Done, I'll watch that for you."),
    ])
    body = client.post("/api/chat", json={"message": "Alert me if Perth-Bali in March drops under 300"}, headers=DEVICE).json()
    assert body["cards"][0]["type"] == "alert"
    alert = db.query(PriceAlert).one()
    assert alert.device_id == DEVICE["X-Device-Id"] and alert.target_price == 300


def test_price_alert_job_triggers_once(db):
    db.add_all([
        PriceAlert(device_id="d1", origin="PER", destination="SYD", depart_month="2026-11", target_price=200, currency="AUD"),
        PriceAlert(device_id="d2", origin="PER", destination="SYD", depart_month="2026-11", target_price=100, currency="AUD"),
    ])
    db.commit()

    async def search(**kw):
        return SAMPLE_FLIGHTS

    sent = []

    async def notify(alert, price, url):
        sent.append((alert.device_id, price, url))

    result = asyncio.run(check_alerts(db, search=search, notify=notify))
    assert result == {"checked": 2, "triggered": 1, "failed": 0}
    assert sent == [("d1", 189.0, SAMPLE_FLIGHTS["results"][0]["url"])]

    # Already-triggered alerts aren't checked again.
    again = asyncio.run(check_alerts(db, search=search, notify=notify))
    assert again["checked"] == 1 and len(sent) == 1
    assert db.query(PriceAlert).filter_by(device_id="d2").one().last_price == 189
