"""Peer shift swap requests (Roadmap v2 Phase 1B)."""
from datetime import date, datetime, timezone
from typing import Any, Optional

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class SwapStatus:
    PENDING_PEER = "pending_peer"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    DECLINED = "declined"
    CANCELLED = "cancelled"

    OPEN = (PENDING_PEER, PENDING_APPROVAL)


class ShiftSwapRequest(Base):
    __tablename__ = "shift_swap_request"  # type: ignore[assignment]
    __table_args__ = (
        Index("ix_shift_swap_cp_status", "counterparty_id", "status"),
        Index("ix_shift_swap_req_status", "requester_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    requester_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    counterparty_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    requester_date: Mapped[date] = mapped_column(Date, nullable=False)
    counterparty_date: Mapped[date] = mapped_column(Date, nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=SwapStatus.PENDING_PEER)
    # Both parties' effective cells on the swap dates at create time:
    # {"a": {iso_date: [template_id|null, is_week_off]}, "b": {...}}.
    # Used to detect "schedule changed" before accept/approve.
    snapshot: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    peer_responded_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True)
    decided_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    decided_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True)
    decision_note: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc), nullable=False)
