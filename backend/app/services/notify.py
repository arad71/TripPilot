"""Alert notifications.

If ALERT_WEBHOOK_URL is set, each triggered alert is POSTed there as JSON. Point it at
Zapier, Make, n8n or your own email service to send the email/SMS/push.
"""
import logging

import httpx

from app.config import settings
from app.models import PriceAlert

log = logging.getLogger(__name__)


async def notify_alert(alert: PriceAlert, price: float, booking_url: str | None) -> None:
    payload = {
        "event": "price_alert_triggered",
        "alert_id": alert.id,
        "device_id": alert.device_id,
        "email": alert.email,
        "route": f"{alert.origin}-{alert.destination}",
        "depart": alert.depart_month,
        "return": alert.return_month,
        "target_price": alert.target_price,
        "price": price,
        "currency": alert.currency,
        "booking_url": booking_url,
    }
    log.info("Price alert triggered: %s", payload)
    if not settings.alert_webhook_url:
        return
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(settings.alert_webhook_url, json=payload)
    if r.status_code >= 400:
        log.warning("Alert webhook failed: %s", r.status_code)
