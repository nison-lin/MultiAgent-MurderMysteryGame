"""数据访问类基类"""
    
from sqlalchemy.orm import Session

from db.entity.base_entity import BaseEntity
from model.base_model import BaseDataModel

class BaseRepository[EntityType: BaseEntity, ModelType: BaseDataModel]:
    """数据访问类基类"""

    def __init__(self, session: Session, entity_cls: type[EntityType], model_cls: type[ModelType]):
        self.session = session
        self.entity_cls = entity_cls
        self.model_cls = model_cls

    def get_by_id(self, id: int) -> EntityType:
        """根据ID获取实体"""
        entity = self.session.get(self.entity_cls, id)
        if not entity:
            raise ValueError("未找到该实体")
        return entity

    def save(self, model: ModelType) -> ModelType:
        """保存实体"""
        entity = self._to_entity(model)
        self.session.add(entity)
        self.session.flush()
        return self._to_model(entity)

    def delete(self, id: int) -> bool:
        """删除实体"""
        entity = self.get_by_id(id)
        if not entity:
            return False
        self.session.delete(entity)
        return True

    def update(self, model: ModelType) -> bool:
        """更新实体"""
        if not model.id:
            return False
        entity = self.get_by_id(model.id)
        if not entity:
            return False
        for key, value in model.to_dict().items():
            setattr(entity, key, value)
        return True

    def _to_entity(self, model: ModelType) -> EntityType:
        """将模型转换为实体"""
        model_dict = model.to_dict()
        return self.entity_cls(**model_dict)

    def _to_model(self, entity: EntityType) -> ModelType:
        """将实体转换为模型"""
        model = self.model_cls.model_validate(entity)
        return model