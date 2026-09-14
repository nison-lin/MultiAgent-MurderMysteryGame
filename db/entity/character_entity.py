"""角色实体类"""

from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..image_storage_type import ImageStorageType

from .base_entity import BaseEntity

if TYPE_CHECKING:
    from .script_entity import ScriptEntity
    from .story_entity import StoryEntity

class CharacterGenderEnum(str, Enum):
    """性别枚举"""
    MALE = "男"
    FEMALE = "女"
    NONHUMAN = "非人类"
    UNKNOWN = "未知"

class CharacterEntity(BaseEntity):
    """角色实体类"""
    __tablename__ = "character"

    name: Mapped[str | None] = mapped_column(String(50))
    gender: Mapped[CharacterGenderEnum | None] = mapped_column()
    age: Mapped[int | None] = mapped_column()
    profession: Mapped[str | None] = mapped_column(String(50))
    background: Mapped[str | None] = mapped_column(String(255))
    is_murderer: Mapped[bool | None] = mapped_column()
    avatar_path: Mapped[str | None] = mapped_column(Text)
    avatar_storage_type: Mapped[ImageStorageType | None] = mapped_column(Text)
    script_id: Mapped[int | None] = mapped_column(ForeignKey("script.id"))

    script: Mapped["ScriptEntity | None"] = relationship("ScriptEntity", back_populates="characters")
    stories: Mapped[list["StoryEntity"]] = relationship("StoryEntity", back_populates="character", cascade="all, delete-orphan")