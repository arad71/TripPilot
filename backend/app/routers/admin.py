"""Owner stats: which features drive affiliate clicks. Protected by ADMIN_TOKEN."""
import hmac
from datetime import timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import AffiliateLink, ChatSession, Click, utcnow

router = APIRouter(prefix="/api/admin", tags=["admin"])


def require_admin(authorization: str = Header(default="")) -> None:
    expected = f"Bearer {settings.admin_token}"
    if not settings.admin_token or not hmac.compare_digest(authorization, expected):
        raise HTTPException(401, "Unauthorized")


@router.get("/stats", dependencies=[Depends(require_admin)])
def stats(days: int = Query(30, ge=1, le=365), db: Session = Depends(get_db)):
    since = utcnow() - timedelta(days=days)

    shown = dict(db.execute(
        select(AffiliateLink.category, func.count(AffiliateLink.id))
        .where(AffiliateLink.created_at >= since)
        .group_by(AffiliateLink.category)
    ).all())
    clicks = dict(db.execute(
        select(AffiliateLink.category, func.count(Click.id))
        .join(Click, Click.link_id == AffiliateLink.id)
        .where(Click.created_at >= since)
        .group_by(AffiliateLink.category)
    ).all())
    sessions = db.scalar(select(func.count(ChatSession.id)).where(ChatSession.created_at >= since))

    categories = sorted(set(shown) | set(clicks))
    return {
        "since": since.isoformat() + "Z",
        "chat_sessions": sessions,
        "by_category": [
            {
                "category": c,
                "links_shown": shown.get(c, 0),
                "clicks": clicks.get(c, 0),
                "click_rate": round(clicks.get(c, 0) / shown[c], 3) if shown.get(c) else None,
            }
            for c in categories
        ],
        "note": "Bookings and commission are reported in each affiliate network's dashboard.",
    }
