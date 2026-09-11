"""背景故事模型"""

from pydantic import Field

from model.base_model import BaseDataModel

class Backstory(BaseDataModel):
    """背景故事模型"""

    content: str = Field(..., description="背景故事内容")
    script_id: int = Field(..., description="剧本ID")