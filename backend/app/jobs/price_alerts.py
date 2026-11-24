"""Check active price alerts and notify when a fare drops to the target.

Run on a schedule (e.g. every 6 hours via cron, a Render/Railway cron job, or
GitHub Actions):  python -m app.jobs.price_alerts
"""
import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal, init_db
from app.models import PriceAlert, utcnow
from app.providers import flights
from app.providers.base import ProviderError
from app.services.notify import notify_alert

log = logging.getLogger(__name__)


async def check_alerts(db: Session, search=None, notify=None) -> dict:
    search = search or flights.search_flights
    notify = notify or notify_alert
    alerts = db.scalars(
        select(PriceAlert).where(PriceAlert.active.is_(True), PriceAlert.triggered_at.is_(None))
    ).all()

    checked = triggered = failed = 0
    for alert in alerts:
        try:
            data = await search(
                origin=alert.origin,
                destination=alert.destination,
                departure_date=alert.depart_month,
                return_date=alert.return_month,
                currency=alert.currency.lower(),
            )
        except ProviderError as e:
            failed += 1
            log.warning("Alert %s check failed: %s", alert.id, e)
            continue

        checked += 1
        alert.last_checked_at = utcnow()
        priced = [r for r in data.get("results", []) if r.get("price") is not None]
        if not priced:
            continue
        best = min(priced, key=lambda r: r["price"])
        alert.last_price = float(best["price"])
        if alert.last_price <= alert.target_price:
            alert.triggered_at = utcnow()
            triggered += 1
            await notify(alert, alert.last_price, best.get("url"))
        db.commit()

    db.commit()
    return {"checked": checked, "triggered": triggered, "failed": failed}


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    init_db()
    with SessionLocal() as db:
        print(asyncio.run(check_alerts(db)))


if __name__ == "__main__":
    main()
