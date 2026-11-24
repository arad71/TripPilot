"""Flight prices via the Travelpayouts / Aviasales Data API.

The Data API returns *cached* fares from recent real searches. It is free and available
as soon as you join Travelpayouts. Prices can be slightly out of date, so the app labels
them "from" and the final price is confirmed on the partner's site. When you're approved
for the real-time Flight Search API, replace `search_flights` here; nothing else changes.
"""
import httpx

from app.config import settings
from app.providers.base import ProviderError, ProviderNotConfigured, ttl_cache

PRICES_URL = "https://api.travelpayouts.com/aviasales/v3/prices_for_dates"
AVIASALES_BASE = "https://www.aviasales.com"


def affiliate_url(relative_link: str) -> str:
    sep = "&" if "?" in relative_link else "?"
    return f"{AVIASALES_BASE}{relative_link}{sep}marker={settings.travelpayouts_marker}"


@ttl_cache(seconds=600)
async def search_flights(
    origin: str,
    destination: str,
    departure_date: str,
    return_date: str | None = None,
    direct_only: bool = False,
    currency: str | None = None,
    limit: int = 5,
) -> dict:
    """origin/destination: IATA codes. Dates: YYYY-MM-DD, or YYYY-MM for a flexible month."""
    if not settings.travelpayouts_token:
        raise ProviderNotConfigured("Flight search is not set up yet (TRAVELPAYOUTS_TOKEN missing).")

    cur = (currency or settings.default_currency).lower()
    params = {
        "origin": origin.upper(),
        "destination": destination.upper(),
        "departure_at": departure_date,
        "one_way": "false" if return_date else "true",
        "direct": "true" if direct_only else "false",
        "currency": cur,
        "sorting": "price",
        "limit": max(1, min(int(limit), 10)),
        "token": settings.travelpayouts_token,
    }
    if return_date:
        params["return_at"] = return_date

    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(PRICES_URL, params=params)
    if r.status_code != 200:
        raise ProviderError(f"Flight search failed ({r.status_code})")

    payload = r.json()
    if not payload.get("success", True):
        raise ProviderError(payload.get("error") or "Flight search failed")

    results = [
        {
            "airline": f.get("airline"),
            "flight_number": f.get("flight_number"),
            "from": f.get("origin_airport") or params["origin"],
            "to": f.get("destination_airport") or params["destination"],
            "departure_at": f.get("departure_at"),
            "return_at": f.get("return_at"),
            "stops": f.get("transfers"),
            "duration_minutes": f.get("duration_to") or f.get("duration"),
            "price": f.get("price"),
            "currency": cur.upper(),
            "url": affiliate_url(f.get("link") or "/"),
        }
        for f in payload.get("data", [])
    ]
    return {
        "type": "flights",
        "origin": params["origin"],
        "destination": params["destination"],
        "price_note": "Recent fares. Final price is confirmed on the booking site.",
        "results": results,
    }
