"""模型基类"""

from abc import ABC
from datetime import datetime
from typing import Optional, Any

from pydantic import BaseModel, Field, ConfigDict

# 由数据库管理的字段：id 自增，created_at 由 server_default 写入，
# updated_at 由 onupdate 刷新。三者都不允许从模型侧写入。
_AUTO_FIELDS = frozenset({"id", "created_at", "updated_at"})

def _is_missing(value: Any) -> bool:
    """判断字段值是否视为缺失：None、空字符串、空列表"""
    return value is None or value == "" or value == []

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
        """将模型转换为字典，id与创建/更新时间由数据库管理，一律剔除"""
        transfered_dict = self.model_dump(exclude_none=True)
        for name in _AUTO_FIELDS:
            transfered_dict.pop(name, None)
        return transfered_dict

    def is_complete(self, strict: bool = False) -> list[str]:
        """返回缺失（None、空字符串、空列表）的字段名，嵌套模型以 a.b 形式给出路径"""
        missing: list[str] = []
        fields = _AUTO_FIELDS if strict else []
        for name in type(self).model_fields:
            if name in _AUTO_FIELDS:
                continue
            value = getattr(self, name)
            if _is_missing(value):
                missing.append(name)
            elif isinstance(value, BaseDataModel):
                # 嵌套模型：递归检查，路径加上当前字段名前缀
                missing.extend(f"{name}.{sub}" for sub in value.is_complete())
            elif isinstance(value, (list, tuple)):
                # 列表元素中的模型：路径带上下标
                for index, item in enumerate(value):
                    if isinstance(item, BaseDataModel):
                        missing.extend(
                            f"{name}[{index}].{sub}" for sub in item.is_complete()
                        )
                    elif _is_missing(item):
                        missing.append(f"{name}[{index}]")
        return missing


class Image(BaseDataModel):
    """图片模型"""

    image_path: str = Field(..., description="图片地址")
    image_storage_type: str = Field(..., description="图片存储类型")