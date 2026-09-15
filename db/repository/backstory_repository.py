"""背景故事数据访问类"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.entity.backstory_entity import BackstoryEntity
from db.repository.base_repository import BaseRepository
from model.backstory import Backstory


class BackstoryRepository(BaseRepository[BackstoryEntity, Backstory]):
    """背景故事数据访问类"""

    def __init__(self, session: Session):
        super().__init__(session, BackstoryEntity, Backstory)
        
    def get_by_script_id(self, script_id: int) -> Backstory | None:
        """根据角色ID获取背景故事"""
        stmt = select(BackstoryEntity).where(BackstoryEntity.script_id == script_id)
        backstory_entity = self.session.execute(stmt).scalar_one_or_none()
        if not backstory_entity:
            return None
        return super()._to_model(backstory_entity)