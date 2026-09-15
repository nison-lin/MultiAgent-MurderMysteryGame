"""数据访问类基类"""
    
from typing import Any

from sqlalchemy.orm import Session

from db.entity.base_entity import BaseEntity
from db.repository.image_mapping import flatten_images, unflatten_images
from model.base_model import BaseDataModel

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
        """保存实体"""
        entity = self._to_entity(model)
        self.session.add(entity)
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
        """更新实体。id与created_at保持不变，updated_at由数据库刷新为当前时间"""
        if not model.id:
            return False
        entity = self.get_entity_by_id(model.id)
        if not entity:
            return False
        self._apply_columns(entity, model)
        self.session.flush()
        return True

    def _to_columns(self, model: BaseDataModel) -> dict[str, Any]:
        """将模型转换为实体列的字典，嵌套Image字段会展开为扁平列"""
        return flatten_images(type(model), model.to_dict())

    def _apply_columns(self, entity: BaseEntity, model: BaseDataModel) -> None:
        """把模型的字段写到既有实体上。不含id与created_at，故主键与创建时间不受影响"""
        for key, value in self._to_columns(model).items():
            setattr(entity, key, value)

    def _merge_collection[AnyEntityType: BaseEntity](
            self,
            existing: list[AnyEntityType],
            models: list[Any],
            entity_cls: type[AnyEntityType]
        ) -> list[AnyEntityType]:
        """按id把模型列表合并进既有实体列表。

        带id且能在既有列表中命中的，就地更新（保留id与created_at）；
        其余作为新行插入。未出现在models中的既有实体不会被返回，
        交由delete-orphan级联删除。
        """
        by_id = {entity.id: entity for entity in existing}
        merged: list[AnyEntityType] = []
        for model in models:
            entity = by_id.pop(model.id, None) if model.id else None
            if entity is not None:
                self._apply_columns(entity, model)
                merged.append(entity)
            else:
                merged.append(self._to_any_entity(model, entity_cls))
        return merged

    def _to_entity(self, model: ModelType) -> EntityType:
        """将模型转换为实体"""
        return self.entity_cls(**self._to_columns(model))

    def _to_any_entity[AnyEntityType: BaseEntity](
            self,
            model: BaseDataModel,
            entity_cls: type[AnyEntityType]
        ) -> AnyEntityType:
        """将任意模型转换为指定的实体类型"""
        return entity_cls(**self._to_columns(model))

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