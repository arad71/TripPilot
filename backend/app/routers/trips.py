"""Trip wallet: saved and booked flights, hotels and extras, per device."""
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import device_id
from app.models import Trip, TripItem
from app.schemas import TripIn, TripItemIn, TripItemOut, TripItemPatch, TripOut

router = APIRouter(prefix="/api/trips", tags=["trips"])


def _trip(db: Session, device: str, trip_id: int) -> Trip:
    trip = db.get(Trip, trip_id)
    if trip is None or trip.device_id != device:
        raise HTTPException(404, "Trip not found")
    return trip


def _item(db: Session, device: str, item_id: int) -> TripItem:
    item = db.get(TripItem, item_id)
    if item is None or item.trip.device_id != device:
        raise HTTPException(404, "Item not found")
    return item


@router.get("", response_model=list[TripOut])
def list_trips(device: str = Depends(device_id), db: Session = Depends(get_db)):
    return db.scalars(select(Trip).where(Trip.device_id == device).order_by(Trip.created_at.desc())).all()


@router.post("", response_model=TripOut, status_code=201)
def create_trip(body: TripIn, device: str = Depends(device_id), db: Session = Depends(get_db)):
    trip = Trip(device_id=device, name=body.name.strip())
    db.add(trip)
    db.commit()
    db.refresh(trip)
    return trip


@router.post("/quick-save", response_model=TripOut, status_code=201)
def quick_save(body: TripItemIn, device: str = Depends(device_id), db: Session = Depends(get_db)):
    """Save a result to the most recent trip, creating "My trips" if there is none."""
    trip = db.scalars(
        select(Trip).where(Trip.device_id == device).order_by(Trip.created_at.desc()).limit(1)
    ).first()
    if trip is None:
        trip = Trip(device_id=device, name="My trips")
        db.add(trip)
        db.flush()
    db.add(TripItem(trip_id=trip.id, **body.model_dump()))
    db.commit()
    db.refresh(trip)
    return trip


@router.post("/{trip_id}/items", response_model=TripItemOut, status_code=201)
def add_item(trip_id: int, body: TripItemIn, device: str = Depends(device_id), db: Session = Depends(get_db)):
    trip = _trip(db, device, trip_id)
    item = TripItem(trip_id=trip.id, **body.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.patch("/items/{item_id}", response_model=TripItemOut)
def update_item(item_id: int, body: TripItemPatch, device: str = Depends(device_id), db: Session = Depends(get_db)):
    item = _item(db, device, item_id)
    item.status = body.status
    db.commit()
    db.refresh(item)
    return item


@router.delete("/items/{item_id}", status_code=204)
def delete_item(item_id: int, device: str = Depends(device_id), db: Session = Depends(get_db)):
    db.delete(_item(db, device, item_id))
    db.commit()
    return Response(status_code=204)


@router.delete("/{trip_id}", status_code=204)
def delete_trip(trip_id: int, device: str = Depends(device_id), db: Session = Depends(get_db)):
    db.delete(_trip(db, device, trip_id))
    db.commit()
    return Response(status_code=204)
