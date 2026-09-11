"""故事模型"""

from pydantic import Field

from model.base_model import BaseDataModel

class Story(BaseDataModel):
    """故事模型"""
    
    content: str = Field(..., description="故事内容")
    chapter: int = Field(..., description="章节")
    character_id: int = Field(..., description="角色ID")