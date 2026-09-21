"""剧本模型"""

from pydantic import Field

from db.entity.script_entity import ScriptStatusEnum, ScriptTypeEnum
from model.backstory import Backstory
from model.base_model import BaseDataModel
from model.base_model import Image
from model.character import Character
from model.evidence import Evidence

class Script(BaseDataModel):
    """剧本模型"""

    title: str | None = Field(None, description="剧本名称")
    description: str | None = Field(None, description="剧本简介")
    duration_hours: int | None = Field(None, description="剧本时长（小时）")
    player_count: int | None = Field(None, description="剧本人数")
    script_type: ScriptTypeEnum | None = Field(None, description="剧本类型")
    status: ScriptStatusEnum | None = Field(ScriptStatusEnum.DRAFT, description="剧本状态")
    cover_image_: Image | None = Field(None, description="封面图片")
    
    # 关联字段：None表示本次不涉及该关联，空列表表示清空
    characters: list[Character] | None = Field(None, description="剧本的角色列表")
    evidences: list[Evidence] | None = Field(None, description="剧本的证据列表")
    backstory: Backstory | None = Field(None, description="剧本的背景故事")