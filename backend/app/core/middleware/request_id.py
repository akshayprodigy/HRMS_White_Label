from __future__ import annotations

import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.request_context import actor_user_id_var, request_id_var


class RequestIdMiddleware(BaseHTTPMiddleware):
    header_name = "X-Request-Id"

    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[override]
        incoming = request.headers.get(self.header_name)
        request_id = incoming.strip() if incoming else uuid.uuid4().hex

        request_id_token = request_id_var.set(request_id)
        actor_token = actor_user_id_var.set(None)
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(request_id_token)
            actor_user_id_var.reset(actor_token)

        response.headers[self.header_name] = request_id
        return response
