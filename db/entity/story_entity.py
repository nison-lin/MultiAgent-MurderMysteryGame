"""故事实体类"""

from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base_entity import BaseEntity

class StoryEntity(BaseEntity):
    """故事实体类"""
    __tablename__ = "story"

    content: Mapped[str | None] = mapped_column(Text)
    chapter: Mapped[int | None] = mapped_column()
    character_id: Mapped[int | None] = mapped_column(ForeignKey("character.id"))

    character: Mapped["CharacterEntity"] = relationship("CharacterEntity", back_populates="stories")