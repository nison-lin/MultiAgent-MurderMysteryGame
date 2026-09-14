"""角色数据访问类"""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.entity.character_entity import CharacterEntity
from db.entity.story_entity import StoryEntity
from db.repository.base_repository import BaseRepository
from error.errors import DBError
from model.character import Character
from model.story import Story

class CharacterRepository(BaseRepository[CharacterEntity, Character]):
    """角色数据访问类"""

    def __init__(self, session: Session):
        super().__init__(session, CharacterEntity, Character)

    def get_by_script_id(self, script_id: int) -> Sequence[Character]:
        """根据剧本ID获取角色列表"""
        stmt = select(CharacterEntity).where(CharacterEntity.script_id == script_id)
        character_entities = self.session.execute(stmt).scalars().all()
        if not character_entities:
            return []
        return [super()._to_model(character_entity) for character_entity in character_entities]

    # 关联方法
    def get_stories(self, character_id: int) -> list[Story]:
        """根据角色ID获取故事列表"""
        character_entity = self.get_entity_by_id(character_id)
        if not character_entity:
            raise DBError("角色不存在")
        return [super()._to_any_model(story_entity, Story) for story_entity in character_entity.stories]

    def update_stories(self, character_id: int, stories: list[Story]) -> bool:
        """更新角色的故事列表"""
        character_entity = self.get_entity_by_id(character_id)
        if not character_entity:
            raise DBError("角色不存在")
        story_entities = [super()._to_any_entity(story, StoryEntity) for story in stories]
        character_entity.stories = story_entities
        self.session.flush()
        return True
    
    def delete_stories(self, character_id: int) -> bool:
        """删除角色的故事列表"""
        character_entity = self.get_entity_by_id(character_id)
        if not character_entity:
            raise DBError("角色不存在")
        character_entity.stories = []
        self.session.flush()
        return True