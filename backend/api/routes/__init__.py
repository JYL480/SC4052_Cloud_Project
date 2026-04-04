from fastapi import FastAPI
from . import start
from . import chat

# Service routers — each service exposes its own endpoints
from services.weather_service import router as weather_router
from services.calendar_service import router as calendar_router
from services.email_service import router as email_router
from services.preference_service import router as preference_router
from services.general_service import router as general_router


def register_routes(app: FastAPI):
    # ── Core API routes ──────────────────────────────────────────────────
    app.include_router(start.router)
    app.include_router(chat.router)

    # ── Service endpoints ────────────────────────────────────────────────
    # Each service is an independent capability exposed as an HTTP endpoint.
    # They can be extracted to separate servers later without code changes.
    app.include_router(weather_router)
    app.include_router(calendar_router)
    app.include_router(email_router)
    app.include_router(preference_router)
    app.include_router(general_router)
