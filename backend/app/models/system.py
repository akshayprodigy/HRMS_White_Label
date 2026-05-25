from sqlalchemy import String, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base_class import Base


class SystemSetting(Base):
    """
    General system settings stored as key-value pairs.
    Used for thresholds, global configuration, etc.
    """
    key: Mapped[str] = mapped_column(String(100), primary_key=True, index=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(String(200))
    metadata_json: Mapped[dict | None] = mapped_column(JSON)
