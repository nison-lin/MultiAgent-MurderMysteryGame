"""背景故事实体类"""

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base_entity import BaseEntity

class BackstoryEntity(BaseEntity):
    """背景故事实体类"""
    __tablename__ = "backstory"

    content: Mapped[str | None] = mapped_column(Text)
    script_id: Mapped[int | None] = mapped_column(ForeignKey("script.id"))

    script: Mapped["ScriptEntity"] = relationship("ScriptEntity", back_populates="backstory")