"""Hotel search.

Day one: a tracked Booking.com search link (needs only your affiliate id, "aid").
Once approved for a hotel content API (Booking.com Demand API, Expedia Rapid, Agoda, or
a Travelpayouts hotel brand), implement `_search_hotel_api` and the app will show real
hotel cards with prices.
"""
from urllib.parse import urlencode

from app.config import settings


def booking_search_url(term: str, check_in: str, check_out: str, adults: int, rooms: int) -> str:
    params = {
        "ss": term,
        "checkin": check_in,
        "checkout": check_out,
        "group_adults": adults,
        "no_rooms": rooms,
    }
    if settings.booking_aid:
        params["aid"] = settings.booking_aid
    return "https://www.booking.com/searchresults.html?" + urlencode(params)


async def _search_hotel_api(**kwargs) -> list[dict]:
    """Return [{"name", "stars", "rating", "area", "distance_km", "price_total",
    "currency", "free_cancellation", "partner", "url"}, ...] from a real hotel API."""
    return []


async def search_hotels(
    city: str,
    check_in: str,
    check_out: str,
    adults: int = 1,
    rooms: int = 1,
    near: str | None = None,
    max_price_per_night: float | None = None,
) -> dict:
    term = f"{near}, {city}" if near else city
    hotels = await _search_hotel_api(
        city=city, check_in=check_in, check_out=check_out, adults=adults,
        rooms=rooms, near=near, max_price=max_price_per_night,
    )
    return {
        "type": "hotels",
        "city": city,
        "near": near,
        "check_in": check_in,
        "check_out": check_out,
        "results": hotels,
        "search_url": booking_search_url(term, check_in, check_out, adults, rooms),
        "note": "" if hotels else (
            "A live hotel list isn't connected yet. The user gets a search link showing "
            "available hotels and prices for these dates. Don't name specific hotels or prices."
        ),
    }
