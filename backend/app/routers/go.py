"""Tracked affiliate redirect: /go/<id> records a click, then sends the user to the partner.

Only URLs we stored ourselves can be redirected to, so this is not an open redirect.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import AffiliateLink, Click

router = APIRouter(tags=["affiliate"])


@router.get("/go/{link_id}")
def go(link_id: str, request: Request, db: Session = Depends(get_db)):
    link = db.get(AffiliateLink, link_id)
    if link is None:
        raise HTTPException(404, "Link not found")
    db.add(Click(
        link_id=link.id,
        user_agent=request.headers.get("user-agent", "")[:300],
        referrer=request.headers.get("referer", "")[:300],
    ))
    db.commit()
    return RedirectResponse(link.url, status_code=302, headers={"X-Robots-Tag": "noindex, nofollow"})
