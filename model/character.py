"""角色模型"""

from pydantic import Field

from db.entity.character_entity import CharacterGenderEnum
from model.base_model import BaseDataModel, Image

class Character(BaseDataModel):
    """角色模型"""

    name: str | None = Field(None, description="角色名称")
    gender: CharacterGenderEnum | None = Field(None, description="角色性别")
    age: int | None = Field(None, description="角色年龄")
    profession: str | None = Field(None, description="角色职业")
    background: str | None = Field(None, description="角色背景")
    is_murderer: bool | None = Field(None, description="是否为凶手")
    avatar_image: Image | None = Field(None, description="角色头像")
    script_id: int | None = Field(None, description="剧本ID")