"""剧本实体类"""

from enum import Enum

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..image_storage_type import ImageStorageType

from .base_entity import BaseEntity

class ScriptTypeEnum(str, Enum):
    """剧本类型枚举"""
    DEDUCTION = "推理"
    EMOTION = "情感"
    HORROR = "恐怖"

class ScriptStatusEnum(str, Enum):
    """剧本状态枚举"""
    DRAFT = "草稿"
    ARCHIVED = "已完成"

class ScriptEntity(BaseEntity):
    """剧本实体类"""
    __tablename__ = "script"

    title: Mapped[str | None] = mapped_column(String(50))
    description: Mapped[str | None] = mapped_column(String(255))
    duration_hours: Mapped[int | None] = mapped_column()
    player_count: Mapped[int | None] = mapped_column()
    script_type: Mapped[ScriptTypeEnum | None] = mapped_column()
    status: Mapped[ScriptStatusEnum | None] = mapped_column(default=ScriptStatusEnum.DRAFT)
    cover_image_path: Mapped[str | None] = mapped_column(Text)
    cover_image_storage_type: Mapped[ImageStorageType | None] = mapped_column(Text)
    
    characters: Mapped[list["CharacterEntity"]] = relationship("CharacterEntity", back_populates="script", cascade="all, delete-orphan")
    backstory: Mapped["BackstoryEntity"] = relationship("BackstoryEntity", back_populates="script", uselist=False, cascade="all, delete-orphan")