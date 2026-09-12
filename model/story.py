"""故事模型"""

from pydantic import Field

from model.base_model import BaseDataModel

class Story(BaseDataModel):
    """故事模型"""
    
    content: str | None = Field(None, description="故事内容")
    chapter: int | None = Field(None, description="章节")
    character_id: int | None = Field(None, description="角色ID")