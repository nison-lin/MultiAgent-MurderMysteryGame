"""模型基类"""

from abc import ABC
from datetime import datetime
from typing import Optional, Any

from pydantic import BaseModel, Field, ConfigDict

class BaseDataModel(BaseModel, ABC):
    """模型基类"""

    model_config = ConfigDict(
        # 允许从ORM对象创建模型
        from_attributes=True,
        # 验证赋值
        validate_assignment=True,
        # 使用枚举值而不是名称
        use_enum_values=True,
        # 允许额外字段但忽略它们
        extra='ignore'
    )

    id: Optional[int] = Field(None, description="id")
    created_at: Optional[datetime] = Field(None, description="创建时间")
    updated_at: Optional[datetime] = Field(None, description="更新时间")

    def to_dict(self) -> dict[str, Any]:
        """将模型转换为字典"""
        dict = self.model_dump(exclude_none=True)
        # 移除自动管理的字段
        dict.pop('id', None)
        dict.pop('created_at', None)
        dict.pop('updated_at', None)
        return dict

    def validate(self) -> bool:
        """验证数据完整性"""
        try:
            json_model = self.model_dump(exclude_none=True)
            self.model_validate(json_model)
            return True
        except Exception:
            return False


class Image:
    """图片模型"""

    image_path: str = Field(..., description="图片地址")
    image_storage_type: str = Field(..., description="图片存储类型")