"""剧本模型"""

from pydantic import Field

from db.entity.script_entity import ScriptStatusEnum, ScriptTypeEnum
from db.image_storage_type import ImageStorageType
from model.base_model import BaseDataModel
from model.base_model import Image

class Script(BaseDataModel):
    """剧本模型"""

    name: str | None = Field(None, description="剧本名称")
    description: str | None = Field(None, description="剧本简介")
    duration_hours: int | None = Field(None, description="剧本时长（小时）")
    player_count: int | None = Field(None, description="剧本人数")
    script_type: ScriptTypeEnum | None = Field(None, description="剧本类型")
    status: ScriptStatusEnum | None = Field(ScriptStatusEnum.DRAFT, description="剧本状态")
    cover_image_: Image | None = Field(None, description="封面图片")