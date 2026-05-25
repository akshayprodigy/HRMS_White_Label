from typing import Optional
from sqlalchemy import String, Integer, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base_class import Base


class RequiredDocumentType(Base):
    """Admin-managed list of document types that every employee must upload.

    `doc_type` mirrors the values stored on EmployeeDocument.doc_type so we
    can compute compliance status without a join table.
    """
    __tablename__ = "required_document_type"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    doc_type: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
