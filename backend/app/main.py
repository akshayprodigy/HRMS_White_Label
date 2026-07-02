from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.api import api_router
from app.core.config import settings
from app.core.logging import setup_logging
from app.core.exceptions import setup_exception_handlers
from app.middleware.request_id import RequestIdMiddleware
from app import models # Force all models to be registered

def create_app() -> FastAPI:
    setup_logging()
    app = FastAPI(
        title=settings.PROJECT_NAME,
        openapi_url=f"{settings.API_V1_STR}/openapi.json"
    )

    # Middleware
    app.add_middleware(RequestIdMiddleware)

    # Set all CORS enabled origins
    if settings.BACKEND_CORS_ORIGINS:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=[str(origin) for origin in settings.BACKEND_CORS_ORIGINS],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    setup_exception_handlers(app)
    app.include_router(api_router, prefix=settings.API_V1_STR)

    # Section L: pick providers from env. Boots as LOG providers by
    # default — no accidental real sends without creds.
    from app.services.notifications_delivery import (
        configure_providers_from_env,
    )
    configure_providers_from_env()

    # Section P: boot the APScheduler loop (env-gated via
    # ENABLE_SCHEDULER; see the note in core/config.py about single
    # worker). Without this, cron jobs only ever run via the manual
    # /admin/jobs/{name}/run-now endpoint.
    if settings.ENABLE_SCHEDULER:

        @app.on_event("startup")
        async def _boot_scheduler() -> None:
            from app.db.session import SessionLocal
            from app.services.scheduler import ensure_jobs, start_scheduler

            try:
                async with SessionLocal() as session:
                    await ensure_jobs(session)
                start_scheduler(SessionLocal)
            except Exception:  # pragma: no cover — never block app boot
                import logging

                logging.getLogger(__name__).exception(
                    "scheduler startup failed; continuing without it"
                )

        @app.on_event("shutdown")
        async def _stop_scheduler() -> None:
            from app.services.scheduler import shutdown_scheduler

            shutdown_scheduler()

    return app
