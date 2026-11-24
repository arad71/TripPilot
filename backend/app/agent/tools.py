"""Tools the LLM can call. Each tool returns data for the model and may add a "card"
(structured results) for the app to display with tracked Book links."""
import copy
import logging
import secrets
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.config import settings
from app.models import AffiliateLink, PriceAlert
from app.providers import extras, flights, hotels, places
from app.providers.base import ProviderError, ProviderNotConfigured

log = logging.getLogger(__name__)


@dataclass
class ToolContext:
    db: Session
    device_id: str
    session_id: str | None = None
    cards: list[dict] = field(default_factory=list)


def track(ctx: ToolContext, url: str, category: str, partner: str, label: str = "") -> str:
    """Store the partner URL and return our /go/<id> redirect, which records the click."""
    link = AffiliateLink(
        id=secrets.token_urlsafe(9),
        session_id=ctx.session_id,
        device_id=ctx.device_id,
        category=category,
        partner=partner,
        label=(label or "")[:200],
        url=url,
    )
    ctx.db.add(link)
    ctx.db.flush()
    return f"{settings.public_base_url}/go/{link.id}"


TOOLS: list[dict] = [
    {
        "name": "resolve_place",
        "description": "Convert a city or airport name into its IATA code. Call before "
        "search_flights unless you already know the exact code.",
        "input_schema": {
            "type": "object",
            "properties": {"name": {"type": "string", "description": "City or airport, e.g. 'Perth'"}},
            "required": ["name"],
        },
    },
    {
        "name": "search_flights",
        "description": "Search fares between two IATA codes. Use for flight-only requests and "
        "as part of trips. Omit return_date for one-way.",
        "input_schema": {
            "type": "object",
            "properties": {
                "origin": {"type": "string", "description": "IATA code, e.g. PER"},
                "destination": {"type": "string", "description": "IATA code, e.g. SYD"},
                "departure_date": {"type": "string", "description": "YYYY-MM-DD, or YYYY-MM if flexible"},
                "return_date": {"type": "string", "description": "YYYY-MM-DD or YYYY-MM"},
                "direct_only": {"type": "boolean"},
                "currency": {"type": "string", "description": "e.g. aud, usd"},
            },
            "required": ["origin", "destination", "departure_date"],
        },
    },
    {
        "name": "search_hotels",
        "description": "Search hotels in a city for given dates. Use for hotel-only requests "
        "and as part of trips. 'near' can be an airport, landmark, venue or street.",
        "input_schema": {
            "type": "object",
            "properties": {
                "city": {"type": "string"},
                "check_in": {"type": "string", "description": "YYYY-MM-DD"},
                "check_out": {"type": "string", "description": "YYYY-MM-DD"},
                "adults": {"type": "integer"},
                "rooms": {"type": "integer"},
                "near": {"type": "string"},
                "max_price_per_night": {"type": "number"},
            },
            "required": ["city", "check_in", "check_out"],
        },
    },
    {
        "name": "get_extra_links",
        "description": "Get partner links for car rental, airport transfers, eSIM, travel "
        "insurance or tours. Use when asked, or after the user accepts an offered extra.",
        "input_schema": {
            "type": "object",
            "properties": {
                "categories": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["car_rental", "transfer", "esim", "insurance", "tours"]},
                },
                "destination": {"type": "string"},
            },
            "required": ["categories"],
        },
    },
    {
        "name": "create_price_alert",
        "description": "Watch a route and notify the user when the fare drops to or below a "
        "target price. Only when the user asks to be alerted or agrees to it.",
        "input_schema": {
            "type": "object",
            "properties": {
                "origin": {"type": "string", "description": "IATA code"},
                "destination": {"type": "string", "description": "IATA code"},
                "depart_month": {"type": "string", "description": "YYYY-MM or YYYY-MM-DD"},
                "return_month": {"type": "string", "description": "YYYY-MM or YYYY-MM-DD, for return trips"},
                "target_price": {"type": "number"},
                "currency": {"type": "string"},
            },
            "required": ["origin", "destination", "depart_month", "target_price"],
        },
    },
]


async def _resolve_place(ctx: ToolContext, name: str) -> dict:
    return await places.resolve_place(name)


async def _search_flights(ctx: ToolContext, **kw) -> dict:
    data = copy.deepcopy(await flights.search_flights(**kw))  # results may be cached: don't mutate
    for f in data["results"]:
        f["booking_link"] = track(ctx, f.pop("url"), "flight", "Aviasales", f"{f['from']}-{f['to']}")
    if data["results"]:
        ctx.cards.append({
            "type": "flights",
            "title": f"{data['origin']} → {data['destination']}",
            "one_way": not kw.get("return_date"),
            "note": data["price_note"],
            "results": data["results"],
        })
    return data


async def _search_hotels(ctx: ToolContext, **kw) -> dict:
    data = copy.deepcopy(await hotels.search_hotels(**kw))
    for h in data["results"]:
        h["booking_link"] = track(ctx, h.pop("url"), "hotel", h.get("partner", "Hotel"), h.get("name", ""))
    where = f"near {data['near']}, {data['city']}" if data.get("near") else data["city"]
    data["search_link"] = track(ctx, data.pop("search_url"), "hotel", "Booking.com", f"Hotels {where}")
    ctx.cards.append({
        "type": "hotels",
        "title": f"Hotels {where}",
        "subtitle": f"{data['check_in']} to {data['check_out']}",
        "results": data["results"],
        "search_link": data["search_link"],
        "search_label": "See available hotels on Booking.com",
    })
    return data


async def _get_extra_links(ctx: ToolContext, categories: list[str], destination: str | None = None) -> dict:
    data = extras.get_extra_links(categories, destination)
    for item in data["results"]:
        item["link"] = track(ctx, item.pop("url"), item["category"], item["partner"], item["label"])
    if data["results"]:
        ctx.cards.append({"type": "extras", "title": "Useful extras", "results": data["results"]})
    return data


async def _create_price_alert(
    ctx: ToolContext,
    origin: str,
    destination: str,
    depart_month: str,
    target_price: float,
    return_month: str | None = None,
    currency: str | None = None,
) -> dict:
    alert = PriceAlert(
        device_id=ctx.device_id,
        origin=origin.upper()[:3],
        destination=destination.upper()[:3],
        depart_month=depart_month[:10],
        return_month=return_month[:10] if return_month else None,
        target_price=float(target_price),
        currency=(currency or settings.default_currency).upper(),
    )
    ctx.db.add(alert)
    ctx.db.flush()
    summary = {
        "id": alert.id, "origin": alert.origin, "destination": alert.destination,
        "depart_month": alert.depart_month, "return_month": alert.return_month,
        "target_price": alert.target_price, "currency": alert.currency,
    }
    ctx.cards.append({"type": "alert", "title": "Price alert set", "alert": summary})
    return {"created": True, "alert": summary}


HANDLERS = {
    "resolve_place": _resolve_place,
    "search_flights": _search_flights,
    "search_hotels": _search_hotels,
    "get_extra_links": _get_extra_links,
    "create_price_alert": _create_price_alert,
}


async def run_tool(name: str, args: dict, ctx: ToolContext) -> dict:
    """Run a tool. Errors are returned to the model (not raised) so it can recover."""
    handler = HANDLERS.get(name)
    if handler is None:
        return {"error": f"Unknown tool: {name}"}
    try:
        return await handler(ctx, **args)
    except ProviderNotConfigured as e:
        return {"error": str(e), "not_configured": True}
    except ProviderError as e:
        return {"error": str(e)}
    except TypeError as e:
        return {"error": f"Invalid arguments for {name}: {e}"}
    except Exception as e:  # network errors, bad partner data...
        log.exception("Tool %s failed", name)
        return {"error": f"{name} failed: {type(e).__name__}"}
