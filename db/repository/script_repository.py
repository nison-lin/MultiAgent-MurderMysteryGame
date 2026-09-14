"""剧本数据访问类"""

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from db.entity.backstory_entity import BackstoryEntity
from db.entity.character_entity import CharacterEntity
from db.entity.evidence_entity import EvidenceEntity
from db.entity.script_entity import ScriptEntity
from db.repository.base_repository import BaseRepository
from error.errors import DataError
from model.backstory import Backstory
from model.character import Character
from model.evidence import Evidence
from model.script import Script

class ScriptRepository(BaseRepository[ScriptEntity, Script]):
    """剧本数据访问类"""

    def __init__(self, session: Session):
        super().__init__(session, ScriptEntity, Script)

    # 关联方法
    def get_evidences(self, script_id: int) -> list[Evidence]:
        """根据剧本ID获取证据列表"""
        script_entity = self.get_entity_by_id(script_id)
        if not script_entity:
            raise DataError("剧本不存在")
        return [super()._to_any_model(evidence_entity, Evidence) for evidence_entity in script_entity.evidences]

    def update_evidences(self, script_id: int, evidences: list[Evidence]) -> bool:
        """更新剧本的证据列表"""
        script_entity = self.get_entity_by_id(script_id)
        if not script_entity:
            raise DataError("剧本不存在")
        evidece_entities = [super()._to_any_entity(evidence, EvidenceEntity, True) for evidence in evidences]
        script_entity.evidences = evidece_entities
        self.session.flush()
        return True

    def delete_evidences(self, script_id: int) -> bool:
        """删除剧本的证据列表"""
        script_entity = self.get_entity_by_id(script_id)
        if not script_entity:
            raise DataError("剧本不存在")
        script_entity.evidences = []
        self.session.flush()
        return True

    def get_evidences_by_chapter(self, script_id: int, chapter: int) -> list[Evidence]:
        """根据剧本ID和章节数获取证据列表"""
        script_entity = self.get_entity_by_id(script_id)
        if not script_entity:
            raise DataError("剧本不存在")
        return [super()._to_any_model(evidence_entity, Evidence) for evidence_entity in script_entity.evidences if evidence_entity.chapter == chapter]

    def delete_evidences_by_chapter(self, script_id: int, chapter: int) -> bool:
        """根据剧本ID和章节数删除证据列表"""
        script_entity = self.get_entity_by_id(script_id)
        if not script_entity:
            raise DataError("剧本不存在")
        script_entity.evidences = [evidence_entity for evidence_entity in script_entity.evidences if evidence_entity.chapter != chapter]
        self.session.flush()
        return True

    def get_characters(self, script_id: int) -> list[Character]:
        """根据剧本ID获取角色列表"""
        script_entity = self.get_entity_by_id(script_id)
        if not script_entity:
            raise DataError("剧本不存在")
        return [super()._to_any_model(character_entity, Character) for character_entity in script_entity.characters]

    def update_characters(self, script_id: int, characters: list[Character]) -> bool:
        """更新剧本的角色列表"""
        script_entity = self.get_entity_by_id(script_id)
        if not script_entity:
            raise DataError("剧本不存在")
        character_entities = [super()._to_any_entity(character, CharacterEntity, True) for character in characters]
        script_entity.characters = character_entities
        self.session.flush()
        return True
    
    def delete_characters(self, script_id: int) -> bool:
        """删除剧本的角色列表"""
        script_entity = self.get_entity_by_id(script_id)
        if not script_entity:
            raise DataError("剧本不存在")
        script_entity.characters = []
        self.session.flush()
        return True
    
    def get_backstory(self, script_id: int) -> Backstory | None:
        """根据剧本ID获取背景故事"""
        script_entity = self.get_entity_by_id(script_id)
        if not script_entity:
            raise DataError("剧本不存在")
        if not script_entity.backstory:
            return None
        return super()._to_any_model(script_entity.backstory, Backstory)

    def update_backstory(self, script_id: int, backstory: Backstory) -> bool:
        """更新剧本的背景故事"""
        script_entity = self.get_entity_by_id(script_id)
        if not script_entity:
            raise DataError("剧本不存在")
        script_entity.backstory = super()._to_any_entity(backstory, BackstoryEntity, True)
        self.session.flush()
        return True
    
    def delete_backstory(self, script_id: int) -> bool:
        """删除剧本的背景故事"""
        script_entity = self.get_entity_by_id(script_id)
        if not script_entity:
            raise DataError("剧本不存在")
        script_entity.backstory = None
        self.session.flush()
        return True