from __future__ import annotations

from contextvars import ContextVar

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
actor_user_id_var: ContextVar[int | None] = ContextVar(
    "actor_user_id",
    default=None,
)


def get_request_id() -> str | None:
    return request_id_var.get()


def get_actor_user_id() -> int | None:
    return actor_user_id_var.get()
