"""Request/response shapes for the API."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

MONTH_OR_DATE = r"^\d{4}-\d{2}(-\d{2})?$"
IATA = r"^[A-Za-z]{3}$"


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    session_id: str | None = None


class ChatOut(BaseModel):
    reply: str
    session_id: str
    cards: list[dict]


class TripIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class TripItemIn(BaseModel):
    kind: str = Field(min_length=1, max_length=32)
    title: str = Field(min_length=1, max_length=200)
    date: str | None = Field(default=None, max_length=40)
    price: float | None = None
    currency: str | None = Field(default=None, max_length=8)
    link: str | None = Field(default=None, max_length=500)
    status: Literal["saved", "booked", "cancelled"] = "saved"
    details: dict = Field(default_factory=dict)


class TripItemPatch(BaseModel):
    status: Literal["saved", "booked", "cancelled"]


class TripItemOut(TripItemIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


class TripOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    created_at: datetime
    items: list[TripItemOut]


class AlertIn(BaseModel):
    origin: str = Field(pattern=IATA)
    destination: str = Field(pattern=IATA)
    depart_month: str = Field(pattern=MONTH_OR_DATE)
    return_month: str | None = Field(default=None, pattern=MONTH_OR_DATE)
    target_price: float = Field(gt=0)
    currency: str | None = Field(default=None, max_length=8)
    email: str | None = Field(default=None, max_length=200)


class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    origin: str
    destination: str
    depart_month: str
    return_month: str | None
    target_price: float
    currency: str
    email: str | None
    active: bool
    last_price: float | None
    last_checked_at: datetime | None
    triggered_at: datetime | None
