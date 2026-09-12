"""角色数据访问类"""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.entity.character_entity import CharacterEntity
from db.entity.story_entity import StoryEntity
from db.repository.base_repository import BaseRepository
from model.character import Character

class CharacterRepository(BaseRepository[CharacterEntity, Character]):
    """角色数据访问类"""

    def __init__(self, session: Session):
        super().__init__(session, CharacterEntity, Character)

    def get_by_script_id(self, script_id: int) -> Sequence[CharacterEntity]:
        """根据剧本ID获取角色列表"""
        stmt = select(CharacterEntity).where(CharacterEntity.script_id == script_id)
        return self.session.execute(stmt).scalars().all()

    # 关联方法
    def get_stories(self, character_id: int) -> list[CharacterEntity] | None:
        """根据角色ID获取故事列表"""
        character = self.get_by_id(character_id)
        return character.stories

    def update_stories(self, character_id: int, stories: list[StoryEntity]) -> bool:
        """更新角色的故事列表"""
        character = self.get_by_id(character_id)
        character.stories = stories
        self.session.flush()
        return True
    
    def delete_stories(self, character_id: int) -> bool:
        """删除角色的故事列表"""
        character = self.get_by_id(character_id)
        character.stories = []
        self.session.flush()
        return True