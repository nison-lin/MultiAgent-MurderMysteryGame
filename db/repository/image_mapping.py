"""模型嵌套Image字段与实体扁平列（*_path / *_storage_type）之间的映射"""

from enum import Enum
from typing import Any

from db.entity.base_entity import BaseEntity
from error.errors import DataError
from model.base_model import BaseDataModel, Image
from model.character import Character
from model.evidence import Evidence
from model.script import Script

# 模型的嵌套Image字段名 -> 实体扁平列的前缀。
# 实体列固定为 {前缀}_path 与 {前缀}_storage_type。
_IMAGE_FIELD_PREFIXES: dict[type[BaseDataModel], dict[str, str]] = {
    Script: {"cover_image_": "cover_image"},
    Character: {"avatar_image": "avatar"},
    Evidence: {"image": "image"},
}

def _path_column(prefix: str) -> str:
    return f"{prefix}_path"

def _storage_type_column(prefix: str) -> str:
    return f"{prefix}_storage_type"

def _to_str(value: Any) -> str:
    """枚举取其值，其余按字符串处理。实体列为SAEnum时读回的是枚举成员，
    直接str()会得到'ImageStorageType.LOCAL'而非'local'。"""
    return value.value if isinstance(value, Enum) else str(value)

def flatten_images(model_cls: type[BaseDataModel], data: dict[str, Any]) -> dict[str, Any]:
    """将字典中的嵌套Image字段展开为实体的扁平列，返回可直接传给实体的新字典。

    未出现在字典中的Image字段会被跳过，以保持部分更新的语义。
    """
    prefixes = _IMAGE_FIELD_PREFIXES.get(model_cls)
    if not prefixes:
        return data

    flattened = dict(data)
    for field_name, prefix in prefixes.items():
        if field_name not in flattened:
            continue
        image = flattened.pop(field_name)
        if image is None:
            flattened[_path_column(prefix)] = None
            flattened[_storage_type_column(prefix)] = None
            continue
        if isinstance(image, Image):
            image = image.model_dump(exclude_none=True)
        if not isinstance(image, dict):
            raise DataError(f"{model_cls.__name__}.{field_name}必须是Image或字典，实际为{type(image).__name__}。")
        flattened[_path_column(prefix)] = image.get("image_path")
        flattened[_storage_type_column(prefix)] = image.get("image_storage_type")
    return flattened

def _pair_children(models: list[Any], entities: list[Any]) -> list[tuple[Any, Any]]:
    """把子模型与子实体一一对应。优先按id匹配，id缺失时退回按下标对齐。"""
    by_id = {getattr(entity, "id", None): entity for entity in entities}
    pairs: list[tuple[Any, Any]] = []
    for index, child_model in enumerate(models):
        entity = by_id.get(child_model.id) if child_model.id is not None else None
        if entity is None:
            entity = entities[index] if index < len(entities) else None
        if entity is not None:
            pairs.append((child_model, entity))
    return pairs

def _unflatten_nested(model: BaseDataModel, entity: BaseEntity) -> None:
    """递归处理关联字段上的嵌套模型，让子模型的Image字段同样被组装。

    模型的关联字段名与实体的relationship同名，据此配对下钻。
    """
    for field_name in type(model).model_fields:
        value = getattr(model, field_name, None)
        if value is None:
            continue
        if isinstance(value, BaseDataModel):
            child_entity = getattr(entity, field_name, None)
            if child_entity is not None:
                unflatten_images(value, child_entity)
        elif isinstance(value, list) and value and isinstance(value[0], BaseDataModel):
            child_entities = getattr(entity, field_name, None) or []
            for child_model, child_entity in _pair_children(value, list(child_entities)):
                unflatten_images(child_model, child_entity)

def unflatten_images(model: BaseDataModel, entity: BaseEntity) -> BaseDataModel:
    """从实体的扁平列组装嵌套Image字段，就地写回模型并返回该模型。

    关联字段上的子模型会递归处理，故Script.characters[i].avatar_image之类
    的嵌套图片也能正确组装。
    """
    _unflatten_nested(model, entity)

    prefixes = _IMAGE_FIELD_PREFIXES.get(type(model))
    if not prefixes:
        return model

    for field_name, prefix in prefixes.items():
        path = getattr(entity, _path_column(prefix), None)
        storage_type = getattr(entity, _storage_type_column(prefix), None)
        if path is None and storage_type is None:
            continue
        if path is None or storage_type is None:
            raise DataError(
                f"{type(entity).__name__}.{prefix}的路径与存储类型必须同时存在，"
                f"实际为path={path!r}、storage_type={storage_type!r}。"
            )
        setattr(model, field_name, Image(image_path=_to_str(path), image_storage_type=_to_str(storage_type)))
    return model
