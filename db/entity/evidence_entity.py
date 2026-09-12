"""证据实体类"""

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..image_storage_type import ImageStorageType

from .base_entity import BaseEntity

class EvidenceEntity(BaseEntity):
    """证据实体类"""
    __tablename__ = "evidence"

    name: Mapped[str | None] = mapped_column(String(255))
    content: Mapped[str | None] = mapped_column(String(255))
    chapter: Mapped[int | None] = mapped_column()
    image_path: Mapped[str | None] = mapped_column(Text)
    image_storage_type: Mapped[ImageStorageType | None] = mapped_column(Text)
    is_public: Mapped[bool | None] = mapped_column()
    script_id: Mapped[int] = mapped_column(ForeignKey("script.id"))

    script: Mapped["ScriptEntity"] = relationship("ScriptEntity", back_populates="evidences")