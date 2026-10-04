"""故事实体类"""

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base_entity import BaseEntity

if TYPE_CHECKING:
    from .character_entity import CharacterEntity

class StoryEntity(BaseEntity):
    """故事实体类"""
    __tablename__ = "story"

    content: Mapped[str | None] = mapped_column(Text)
    chapter: Mapped[int | None] = mapped_column()
    is_end: Mapped[bool | None] = mapped_column()
    character_id: Mapped[int | None] = mapped_column(ForeignKey("character.id"))

    character: Mapped["CharacterEntity | None"] = relationship("CharacterEntity", back_populates="stories")