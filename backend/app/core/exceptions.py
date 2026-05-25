from typing import Any, Dict
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

import logging
import traceback
from app.core.config import settings

logger = logging.getLogger(__name__)

def setup_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        logger.error(f"HTTP error: {exc.detail}")
        if isinstance(exc.detail, dict) and "error" in exc.detail:
            return JSONResponse(
                status_code=exc.status_code,
                content=exc.detail,
            )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": str(exc.status_code),
                    "message": exc.detail,
                    "details": {}
                }
            },
        )

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.error(f"Global error: {exc}")
        logger.error(traceback.format_exc())
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_SERVER_ERROR",
                    "message": f"Unexpected error: {str(exc)}",
                    "details": {
                        "error_type": type(exc).__name__,
                        "traceback": traceback.format_exc() if settings.LOG_LEVEL == "DEBUG" else None
                    }
                }
            },
        )
