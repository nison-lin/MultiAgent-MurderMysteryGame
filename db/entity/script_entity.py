"""剧本实体类"""

from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Enum as SAEnum

from ..image_storage_type import ImageStorageType

from .base_entity import BaseEntity

if TYPE_CHECKING:
    from .backstory_entity import BackstoryEntity
    from .character_entity import CharacterEntity
    from .evidence_entity import EvidenceEntity

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
    script_type: Mapped[ScriptTypeEnum | None] = mapped_column(
        SAEnum(ScriptTypeEnum, values_callable=lambda e: [m.value for m in e],validate_strings=True)
    )
    status: Mapped[ScriptStatusEnum | None] = mapped_column(
        SAEnum(ScriptStatusEnum, values_callable=lambda e: [m.value for m in e],validate_strings=True),
        default=ScriptStatusEnum.DRAFT
    )
    cover_image_path: Mapped[str | None] = mapped_column(Text)
    cover_image_storage_type: Mapped[ImageStorageType | None] = mapped_column(Text)
    
    characters: Mapped[list["CharacterEntity"]] = relationship("CharacterEntity", back_populates="script", cascade="all, delete-orphan")
    backstory: Mapped["BackstoryEntity | None"] = relationship("BackstoryEntity", back_populates="script", cascade="all, delete-orphan")
    evidences: Mapped[list["EvidenceEntity"]] = relationship("EvidenceEntity", back_populates="script", cascade="all, delete-orphan")