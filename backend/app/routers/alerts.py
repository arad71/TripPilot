from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.deps import device_id
from app.models import PriceAlert
from app.schemas import AlertIn, AlertOut

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.get("", response_model=list[AlertOut])
def list_alerts(device: str = Depends(device_id), db: Session = Depends(get_db)):
    return db.scalars(
        select(PriceAlert).where(PriceAlert.device_id == device).order_by(PriceAlert.created_at.desc())
    ).all()


@router.post("", response_model=AlertOut, status_code=201)
def create_alert(body: AlertIn, device: str = Depends(device_id), db: Session = Depends(get_db)):
    alert = PriceAlert(
        device_id=device,
        origin=body.origin.upper(),
        destination=body.destination.upper(),
        depart_month=body.depart_month,
        return_month=body.return_month,
        target_price=body.target_price,
        currency=(body.currency or settings.default_currency).upper(),
        email=body.email,
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return alert


@router.delete("/{alert_id}", status_code=204)
def delete_alert(alert_id: int, device: str = Depends(device_id), db: Session = Depends(get_db)):
    alert = db.get(PriceAlert, alert_id)
    if alert is None or alert.device_id != device:
        raise HTTPException(404, "Alert not found")
    db.delete(alert)
    db.commit()
    return Response(status_code=204)
