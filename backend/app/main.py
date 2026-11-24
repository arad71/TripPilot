"""TripPilot API server. Also serves the web app from ../frontend."""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.db import init_db
from app.routers import admin, alerts, chat, go, telegram, trips

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=logging.INFO)
    init_db()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="TripPilot", version="0.1.0", lifespan=lifespan)

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @app.get("/api/health", tags=["meta"])
    def health():
        return {
            "ok": True,
            "ai": bool(settings.anthropic_api_key),
            "flights": bool(settings.travelpayouts_token),
            "hotels_affiliate": bool(settings.booking_aid),
            "extras": sorted(k for k, v in settings.extra_links.items() if v),
            "telegram": bool(settings.telegram_bot_token),
        }

    for module in (chat, trips, alerts, go, admin, telegram):
        app.include_router(module.router)

    if FRONTEND_DIR.is_dir():  # mount last so API routes win
        app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="web")
    return app


app = create_app()
