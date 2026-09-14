"""故事数据访问类"""

from collections.abc import Sequence

from sqlalchemy.orm import Session
from sqlalchemy import  select

from db.repository.base_repository import BaseRepository
from model.story import Story
from db.entity.story_entity import StoryEntity

class StoryRepository(BaseRepository[StoryEntity, Story]):
    """故事数据访问类"""

    def __init__(self, session: Session):
        super().__init__(session, StoryEntity, Story)

    def get_by_character_id(self, character_id: int) -> Sequence[Story]:
        """根据角色ID获取故事列表"""
        stmt = select(StoryEntity).where(StoryEntity.character_id == character_id)
        story_entities = self.session.execute(stmt).scalars().all()
        if not story_entities:
            return []
        return [super()._to_model(story_entity) for story_entity in story_entities]