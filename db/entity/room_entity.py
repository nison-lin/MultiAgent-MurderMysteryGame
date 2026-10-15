"""游戏房间实体类"""

from enum import Enum

from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Enum as SAEnum

from db.entity.base_entity import BaseEntity

class PhaseEnum(str, Enum):
    READ = "阅读"
    SEARCH = "搜证"
    TALK = "讨论"
    PRIVATE = "私聊"
    IDENTIFY = "指认"

class StatusEnum(str, Enum):
    IN_PROGRESS = "进行中"
    FINISHED = "已结束"

class RoomEntity(BaseEntity):
    """游戏房间实体类"""
    __tablename__ = "room"

    script_id: Mapped[int | None] = mapped_column()
    chapter: Mapped[int | None] = mapped_column()
    phase: Mapped[PhaseEnum | None] = mapped_column(
        SAEnum(PhaseEnum, values_callable=lambda e: [m.value for m in e],validate_strings=True)
    )
    status: Mapped[StatusEnum | None] = mapped_column(
        SAEnum(StatusEnum, values_callable=lambda e: [m.value for m in e],validate_strings=True)
    )