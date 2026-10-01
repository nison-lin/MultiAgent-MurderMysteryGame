"""游戏房间模型"""

from pydantic import Field

from db.entity.room_entity import PhaseEnum, StatusEnum
from model.base_model import BaseDataModel

class Room(BaseDataModel):
    """游戏房间模型"""

    script_id: int | None = Field(None, description="剧本ID")
    chapter: int | None = Field(None, description="章节")
    phase: PhaseEnum | None = Field(None, description="当前阶段")
    status: StatusEnum | None = Field(StatusEnum.IN_PROGRESS, description="房间状态")