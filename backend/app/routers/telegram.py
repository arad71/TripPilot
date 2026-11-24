"""Telegram bot channel: the same agent, in chat.

Set TELEGRAM_BOT_TOKEN and TELEGRAM_WEBHOOK_SECRET, then register the webhook once:
  curl "https://api.telegram.org/bot<TOKEN>/setWebhook" \
       -d url=<PUBLIC_BASE_URL>/api/telegram/webhook -d secret_token=<SECRET>
"""
import hmac
import logging

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.agent.llm import LLMClient, LLMError
from app.config import settings
from app.db import get_db
from app.deps import optional_llm_client
from app.services.chat_service import get_or_create_session, handle_message, latest_session

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/telegram", tags=["telegram"])

WELCOME = (
    "Hi, I'm TripPilot. Tell me what you need: a flight, a hotel tonight, a car, "
    "an eSIM, or a whole trip.\n\nExample: cheapest flight Perth to Sydney this Friday.\n"
    "Send /new to start a fresh conversation."
)
DISCLOSURE = "We may earn a commission when you book through our links, at no extra cost to you."
TELEGRAM_LIMIT = 4000


def cards_to_text(cards: list[dict]) -> str:
    lines: list[str] = []
    for card in cards:
        lines.append(f"\n{card.get('title', '')}")
        if card["type"] == "flights":
            for f in card["results"][:5]:
                stops = "direct" if f.get("stops") == 0 else f"{f.get('stops')} stop(s)"
                when = (f.get("departure_at") or "")[:16].replace("T", " ")
                lines.append(f"- {f.get('airline')} {stops}, {when}: {f.get('currency')} {f.get('price')}\n  Book: {f['booking_link']}")
        elif card["type"] == "hotels":
            for h in card["results"][:5]:
                lines.append(f"- {h.get('name')}: {h.get('currency', '')} {h.get('price_total', '')}\n  Book: {h['booking_link']}")
            lines.append(f"{card['search_label']}: {card['search_link']}")
        elif card["type"] == "extras":
            for x in card["results"]:
                lines.append(f"- {x['label']}: {x['link']}")
        elif card["type"] == "alert":
            a = card["alert"]
            lines.append(f"{a['origin']} → {a['destination']}, {a['depart_month']}, below {a['currency']} {a['target_price']:g}")
    return "\n".join(lines)


async def send_message(chat_id: int, text: str) -> None:
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(url, json={"chat_id": chat_id, "text": text[:TELEGRAM_LIMIT], "disable_web_page_preview": True})
    if r.status_code != 200:
        log.warning("Telegram sendMessage failed: %s %s", r.status_code, r.text[:200])


@router.post("/webhook")
async def webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str = Header(default=""),
    db: Session = Depends(get_db),
    llm: LLMClient | None = Depends(optional_llm_client),
):
    if not settings.telegram_bot_token:
        raise HTTPException(404, "Telegram is not enabled")
    if settings.telegram_webhook_secret and not hmac.compare_digest(
        x_telegram_bot_api_secret_token, settings.telegram_webhook_secret
    ):
        raise HTTPException(401, "Bad secret")

    update = await request.json()
    message = update.get("message") or {}
    text = (message.get("text") or "").strip()
    chat_id = (message.get("chat") or {}).get("id")
    if not text or chat_id is None:
        return {"ok": True}  # ignore stickers, edits, etc.

    device = f"tg-{chat_id}"
    if text.startswith("/start"):
        await send_message(chat_id, WELCOME)
        return {"ok": True}
    if llm is None:
        await send_message(chat_id, "Sorry, the assistant isn't available right now.")
        return {"ok": True}

    current = None if text.startswith("/new") else latest_session(db, device)
    session = get_or_create_session(db, device, current.id if current else None)
    if text.startswith("/new"):
        db.commit()
        await send_message(chat_id, "Started a new conversation. Where do you need to go?")
        return {"ok": True}

    try:
        result = await handle_message(db, llm, device, text[:2000], session)
    except LLMError:
        db.rollback()
        await send_message(chat_id, "Sorry, something went wrong. Please try again in a moment.")
        return {"ok": True}

    reply = result.reply + cards_to_text(result.cards)
    if result.cards:
        reply += f"\n\n{DISCLOSURE}"
    await send_message(chat_id, reply)
    return {"ok": True}
