"""数据访问类基类"""

from functools import lru_cache
from typing import Any

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from db.entity.base_entity import BaseEntity
from db.repository.image_mapping import flatten_images, unflatten_images
from model.base_model import BaseDataModel

@lru_cache(maxsize=None)
def _column_keys(entity_cls: type[BaseEntity]) -> frozenset[str]:
    """实体上真正的列名集合，不含relationship。mapper配置后不再变化，故缓存。"""
    return frozenset(attr.key for attr in inspect(entity_cls).mapper.column_attrs)

@lru_cache(maxsize=None)
def _relations(entity_cls: type[BaseEntity]) -> dict[str, tuple[type[BaseEntity], bool]]:
    """实体上的relationship：字段名 -> (对端实体类, 是否为集合)。

    模型的关联字段与实体的relationship同名，据此把模型上的关联写回实体。
    """
    return {
        relation.key: (relation.mapper.class_, bool(relation.uselist))
        for relation in inspect(entity_cls).mapper.relationships
    }

class BaseRepository[EntityType: BaseEntity, ModelType: BaseDataModel]:
    """数据访问类基类"""

    def __init__(self, session: Session, entity_cls: type[EntityType], model_cls: type[ModelType]):
        self.session = session
        self.entity_cls = entity_cls
        self.model_cls = model_cls

    def get_by_id(self, id: int) -> ModelType | None:
        """根据ID获取模型"""
        entity = self.session.get(self.entity_cls, id)
        if not entity:
            return None
        return self._to_model(entity)

    def get_entity_by_id(self, id: int) -> EntityType | None:
        """根据ID获取实体"""
        return self.session.get(self.entity_cls, id)

    def save(self, model: ModelType) -> ModelType:
        """保存实体。模型上非None的关联字段会一并级联写入"""
        entity = self._to_entity(model)
        self.session.add(entity)
        self._apply_relations(entity, model)
        self.session.flush()
        return self._to_model(entity)

    def delete(self, id: int) -> bool:
        """删除实体"""
        entity = self.get_entity_by_id(id)
        if not entity:
            return False
        self.session.delete(entity)
        return True

    def update(self, model: ModelType) -> bool:
        """更新实体。id与created_at保持不变，updated_at由数据库刷新为当前时间。

        关联字段为None时保持原样，非None时级联更新（带id的就地更新，
        缺失的旧行由delete-orphan删除）。
        """
        if not model.id:
            return False
        entity = self.get_entity_by_id(model.id)
        if not entity:
            return False
        self._apply_columns(entity, model)
        self._apply_relations(entity, model)
        self.session.flush()
        return True

    def _to_columns(self, model: BaseDataModel, entity_cls: type[BaseEntity]) -> dict[str, Any]:
        """将模型转换为实体列的字典，嵌套Image字段会展开为扁平列。
        """
        columns = flatten_images(type(model), model.to_dict())
        allowed = _column_keys(entity_cls)
        return {key: value for key, value in columns.items() if key in allowed}

    def _apply_columns(self, entity: BaseEntity, model: BaseDataModel) -> None:
        """把模型的字段写到既有实体上。不含id与created_at，故主键与创建时间不受影响"""
        for key, value in self._to_columns(model, type(entity)).items():
            setattr(entity, key, value)

    def _apply_relations(self, entity: BaseEntity, model: BaseDataModel) -> None:
        """把模型上的关联字段级联写到实体上。

        None表示本次不涉及该关联，保持原样；空列表表示清空。
        集合关联按id合并，标量关联已存在时就地更新、否则新建。
        子模型自身的关联会递归处理，故Script.characters[i].stories同样生效。
        """
        relations = _relations(type(entity))
        for field_name, (target_cls, is_collection) in relations.items():
            if field_name not in type(model).model_fields:
                continue
            value = getattr(model, field_name, None)
            if value is None:
                continue
            if is_collection:
                setattr(entity, field_name, self._merge_collection(
                    list(getattr(entity, field_name) or []), list(value), target_cls
                ))
            else:
                existing = getattr(entity, field_name, None)
                if existing is not None:
                    self._apply_columns(existing, value)
                    self._apply_relations(existing, value)
                else:
                    setattr(entity, field_name, self._to_any_entity(value, target_cls))

    def _merge_collection[AnyEntityType: BaseEntity](
            self,
            existing: list[AnyEntityType],
            models: list[Any],
            entity_cls: type[AnyEntityType]
        ) -> list[AnyEntityType]:
        """按id把模型列表合并进既有实体列表。
        """
        by_id = {entity.id: entity for entity in existing}
        merged: list[AnyEntityType] = []
        for model in models:
            entity = by_id.pop(model.id, None) if model.id else None
            if entity is None:
                entity = self._to_any_entity(model, entity_cls)
            else:
                self._apply_columns(entity, model)
            self._apply_relations(entity, model)
            merged.append(entity)
        return merged

    def _to_entity(self, model: ModelType) -> EntityType:
        """将模型转换为实体"""
        return self.entity_cls(**self._to_columns(model, self.entity_cls))

    def _to_any_entity[AnyEntityType: BaseEntity](
            self,
            model: BaseDataModel,
            entity_cls: type[AnyEntityType]
        ) -> AnyEntityType:
        """将任意模型转换为指定的实体类型"""
        return entity_cls(**self._to_columns(model, entity_cls))

    def _to_model(self, entity: EntityType) -> ModelType:
        """将实体转换为模型"""
        model = self.model_cls.model_validate(entity)
        unflatten_images(model, entity)
        return model

    def _to_any_model[AnyModelType: BaseDataModel](
            self,
            entity: BaseEntity,
            model_cls: type[AnyModelType]
        ) -> AnyModelType:
        """将任意实体转换为指定的模型类型"""
        model = model_cls.model_validate(entity)
        unflatten_images(model, entity)
        return model