"""证据模型"""

from pydantic import Field

from model.base_model import BaseDataModel
from model.base_model import Image

class Evidence(BaseDataModel):
    """证据模型"""

    name: str | None = Field(None, description="证据名称")
    content: str | None = Field(None, description="证据内容")
    chapter: int | None = Field(None, description="证据章节")
    image: Image | None = Field(None, description="证据图片")
    is_public: bool | None = Field(None, description="是否公开")
    script_id: int | None = Field(None, description="剧本ID")