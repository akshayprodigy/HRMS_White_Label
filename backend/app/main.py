from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_v1_router
from app.core.config import get_settings
from app.core.middleware.request_id import RequestIdMiddleware


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(title="United Exploration ERP API")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.add_middleware(RequestIdMiddleware)

    app.include_router(api_v1_router, prefix=settings.api_v1_prefix)
    return app


app = create_app()
