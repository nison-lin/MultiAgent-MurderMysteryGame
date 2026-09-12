"""剧本数据访问类"""

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from db.entity.character_entity import CharacterEntity
from db.entity.evidence_entity import EvidenceEntity
from db.entity.script_entity import ScriptEntity
from db.repository.base_repository import BaseRepository
from model.backstory import Backstory
from model.script import Script

class ScriptRepository(BaseRepository[ScriptEntity, Script]):
    """剧本数据访问类"""

    def __init__(self, session: Session):
        super().__init__(session, ScriptEntity, Script)

    # 关联方法
    def get_evidences(self, script_id: int) -> list[EvidenceEntity] | None:
        """根据剧本ID获取证据列表"""
        script = self.get_by_id(script_id)
        return script.evidences

    def update_evidences(self, script_id: int, evidences: list[EvidenceEntity]) -> bool:
        """更新剧本的证据列表"""
        script = self.get_by_id(script_id)
        script.evidences = evidences
        self.session.flush()
        return True

    def delete_evidences(self, script_id: int) -> bool:
        """删除剧本的证据列表"""
        script = self.get_by_id(script_id)
        script.evidences = []
        self.session.flush()
        return True

    def get_evidences_by_chapter(self, script_id: int, chapter: int) -> list[EvidenceEntity] | None:
        """根据剧本ID和章节数获取证据列表"""
        script = self.get_by_id(script_id)
        return [evidence for evidence in script.evidences if evidence.chapter == chapter]

    def delete_evidences_by_chapter(self, script_id: int, chapter: int) -> bool:
        """根据剧本ID和章节数删除证据列表"""
        script = self.get_by_id(script_id)
        script.evidences = [evidence for evidence in script.evidences if evidence.chapter != chapter]
        self.session.flush()
        return True

    def get_characters(self, script_id: int) -> list[CharacterEntity] | None:
        """根据剧本ID获取角色列表"""
        script = self.get_by_id(script_id)
        return script.characters

    def update_characters(self, script_id: int, characters: list[CharacterEntity]) -> bool:
        """更新剧本的角色列表"""
        script = self.get_by_id(script_id)
        script.characters = characters
        self.session.flush()
        return True
    
    def delete_characters(self, script_id: int) -> bool:
        """删除剧本的角色列表"""
        script = self.get_by_id(script_id)
        script.characters = []
        self.session.flush()
        return True
    
    def get_backstory(self, script_id: int) -> Backstory | None:
        """根据剧本ID获取背景故事"""
        script = self.get_by_id(script_id)
        return script.backstory

    def update_backstory(self, script_id: int, backstory: Backstory) -> bool:
        """更新剧本的背景故事"""
        script = self.get_by_id(script_id)
        script.backstory = backstory
        self.session.flush()
        return True
    
    def delete_backstory(self, script_id: int) -> bool:
        """删除剧本的背景故事"""
        script = self.get_by_id(script_id)
        script.backstory = ""
        self.session.flush()
        return True