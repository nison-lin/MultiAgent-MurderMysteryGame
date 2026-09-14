"""背景故事实体类"""

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base_entity import BaseEntity

if TYPE_CHECKING:
    from .script_entity import ScriptEntity

class BackstoryEntity(BaseEntity):
    """背景故事实体类"""
    __tablename__ = "backstory"

    content: Mapped[str | None] = mapped_column(Text)
    script_id: Mapped[int | None] = mapped_column(ForeignKey("script.id"))

    script: Mapped["ScriptEntity | None"] = relationship("ScriptEntity", back_populates="backstory")