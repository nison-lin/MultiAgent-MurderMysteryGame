"""故事模型"""

from pydantic import Field

from model.base_model import BaseDataModel

class Story(BaseDataModel):
    """故事模型"""
    
    content: str | None = Field(default=None, description="故事内容")
    chapter: int | None = Field(default=None, description="章节")
    is_end: bool | None = Field(default=None, description="是否为结尾章节")
    character_id: int | None = Field(default=None, description="角色ID")