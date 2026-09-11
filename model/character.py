"""角色模型"""

from pydantic import Field

from db.entity.character_entity import CharacterGenderEnum
from model.base_model import BaseDataModel, Image

class Character(BaseDataModel):
    """角色模型"""

    name: str = Field(..., description="角色名称")
    gender: CharacterGenderEnum = Field(..., description="角色性别")
    age: int = Field(..., description="角色年龄")
    profession: str = Field(..., description="角色职业")
    background: str = Field(..., description="角色背景")
    is_murderer: bool = Field(..., description="是否为凶手")
    avatar_image: Image | None = Field(None, description="角色头像")
    script_id: int = Field(..., description="剧本ID")