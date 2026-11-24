"""City/airport name -> IATA code ("Perth" -> "PER"), via Travelpayouts autocomplete."""
import httpx

from app.providers.base import ProviderError, ttl_cache

AUTOCOMPLETE_URL = "https://autocomplete.travelpayouts.com/places2"


@ttl_cache(seconds=24 * 3600)
async def resolve_place(name: str, locale: str = "en") -> dict:
    params = {"term": name, "locale": locale, "types[]": ["city", "airport"]}
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(AUTOCOMPLETE_URL, params=params)
    if r.status_code != 200:
        raise ProviderError(f"Place lookup failed ({r.status_code})")

    results = r.json()
    if not results:
        return {"found": False, "query": name}

    top = results[0]
    return {
        "found": True,
        "query": name,
        "code": top.get("code"),
        "name": top.get("name"),
        "type": top.get("type"),
        "country": top.get("country_name"),
        "alternatives": [
            {"code": p.get("code"), "name": p.get("name"), "country": p.get("country_name")}
            for p in results[1:4]
        ],
    }
