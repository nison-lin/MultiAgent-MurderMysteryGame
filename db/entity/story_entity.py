"""故事实体类"""

from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base_entity import BaseEntity

class StoryEntity(BaseEntity):
    """故事实体类"""
    __tablename__ = "story"

    content: Mapped[str] = mapped_column(Text)
    chapter: Mapped[int] = mapped_column()
    script_id: Mapped[int] = mapped_column(ForeignKey("script.id"))

    script: Mapped["ScriptEntity"] = relationship("ScriptEntity", back_populates="stories")
    evidences: Mapped[list["EvidenceEntity"]] = relationship("EvidenceEntity", back_populates="story", cascade="all, delete-orphan")