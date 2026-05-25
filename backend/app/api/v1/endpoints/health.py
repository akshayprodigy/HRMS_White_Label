from typing import Any
from fastapi import APIRouter

router = APIRouter()

@router.get("", response_model=dict)
def health_check() -> Any:
    """
    Health check endpoint.
    """
    return {"status": "ok"}
