"""证据模型"""

from pydantic import Field

from db.image_storage_type import ImageStorageType
from model.base_model import BaseDataModel
from model.base_model import Image

class Evidence(BaseDataModel):
    """证据模型"""

    name: str = Field(..., description="证据名称")
    content: str | None = Field(None, description="证据内容")
    image: Image | None = Field(None, description="证据图片")
    is_public: bool = Field(..., description="是否公开")
    script_id: int = Field(..., description="剧本ID")