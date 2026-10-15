"""游戏流程的数据访问：主持方读取剧本、维护房间都经由此处，测试时可替换为假实现"""

from dataclasses import dataclass, field

from db.database import get_session
from db.entity.room_entity import PhaseEnum, StatusEnum
from db.repository import RoomRepository, ScriptRepository, StoryRepository
from error.errors import DataError
from model.backstory import Backstory
from model.character import Character
from model.evidence import Evidence
from model.room import Room
from model.script import Script
from model.story import Story


@dataclass
class ScriptBundle:
    """开始游戏时一次性读取的剧本数据"""
    script: Script
    characters: list[Character]
    backstory: Backstory | None
    # 角色ID -> 该角色的各章剧本
    stories: dict[int, list[Story]] = field(default_factory=dict)

    def story_of(self, character_id: int, chapter: int) -> Story | None:
        """某个角色某一章的剧本"""
        return next((s for s in self.stories.get(character_id, []) if s.chapter == chapter), None)


class GameData:
    """主持方的数据访问，每个方法使用独立的数据库会话"""

    def load_script(self, script_id: int) -> ScriptBundle:
        """读取剧本、角色、背景故事与全部角色的剧本"""
        with get_session() as session:
            script_repository = ScriptRepository(session)
            script = script_repository.get_by_id(script_id)
            if script is None:
                raise DataError(f"剧本 {script_id} 不存在")
            characters = script_repository.get_characters(script_id)
            backstory = script_repository.get_backstory(script_id)
            story_repository = StoryRepository(session)
            stories = {
                c.id: list(story_repository.get_by_character_id(c.id)) for c in characters if c.id is not None
            }
        return ScriptBundle(script, characters, backstory, stories)

    def load_evidences(self, script_id: int, chapter: int) -> list[Evidence]:
        """读取某一章的证据"""
        with get_session() as session:
            return ScriptRepository(session).get_evidences_by_chapter(script_id, chapter)

    def create_room(self, script_id: int) -> Room:
        """新建一个进行中的房间"""
        with get_session() as session:
            return RoomRepository(session).save(Room(script_id=script_id, chapter=0, status=StatusEnum.IN_PROGRESS))

    def update_room(self, room_id: int, chapter: int, phase: PhaseEnum) -> None:
        """更新房间的章节与阶段"""
        with get_session() as session:
            repository = RoomRepository(session)
            room = repository.get_by_id(room_id)
            if room is None:
                raise DataError(f"房间 {room_id} 不存在")
            room.chapter = chapter
            room.phase = phase
            repository.update(room)

    def finish_room(self, room_id: int) -> None:
        """把房间标记为已结束"""
        with get_session() as session:
            RoomRepository(session).finish(room_id)
