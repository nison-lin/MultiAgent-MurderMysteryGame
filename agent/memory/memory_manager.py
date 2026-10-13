"""记忆管理器"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agent.memory.base_memory import MEMORY_REGISTRY, BaseMemory
from agent.memory.memory_enum import AgentTypeEnum, MemoryCategoryEnum, MemoryTypeEnum, VisibilityEnum
from agent.memory.memory_store import GameClock, MemoryItem, MemoryStore
from error.errors import DataError
from model.character import Character
from model.evidence import Evidence
from model.story import Story

# 系统写入记忆时使用的来源
SYSTEM_SOURCE = "系统"


@dataclass
class _GameMemory:
    """一局游戏的全部记忆"""
    clock: GameClock = field(default_factory=GameClock)
    public_store: MemoryStore = field(default_factory=MemoryStore)
    role_stores: dict[str, MemoryStore] = field(default_factory=dict)
    agent_memories: dict[tuple[str, AgentTypeEnum], BaseMemory] = field(default_factory=dict)


class MemoryManager:
    """
    记忆管理器，按 游戏 -> 角色 -> Agent类型 管理记忆实例，负责：
        1. 隔离：每个角色只能拿到自己的记忆实例，实例中只有本角色的私有存储
        2. 系统写入：剧本、身份、证据、系统公告等由游戏流程写入，而非 Agent 自己写入
        3. 跨角色写入：私聊消息需要同时写入双方的记忆，只能经由管理器完成
        4. 轮次推进与 JSON 持久化
    """

    def __init__(self, short_term_size: int = 50):
        """:param short_term_size: 每个 Agent 短期记忆的条数上限"""
        self.short_term_size = short_term_size
        self._games: dict[str, _GameMemory] = {}

    # ---------------- 游戏与角色 ----------------

    def create_game(self, game_id: str, role_ids: list[str] | None = None) -> None:
        """创建一局游戏的记忆空间，并注册初始角色"""
        if game_id in self._games:
            raise DataError(f"游戏 {game_id} 的记忆已存在")
        self._games[game_id] = _GameMemory()
        for role_id in role_ids or []:
            self.register_role(game_id, role_id)

    def remove_game(self, game_id: str) -> None:
        """游戏结束后释放该局的全部记忆"""
        self._games.pop(game_id, None)

    def register_role(self, game_id: str, role_id: str) -> None:
        """注册角色（玩家角色或 DM），重复注册不影响已有记忆"""
        self._game(game_id).role_stores.setdefault(role_id, MemoryStore())

    def roles(self, game_id: str) -> list[str]:
        """已注册的角色"""
        return list(self._game(game_id).role_stores)

    def get_agent_memory(self, game_id: str, role_id: str, agent_type: AgentTypeEnum) -> BaseMemory:
        """获取某个角色某类 Agent 的记忆，不存在时按注册表创建"""
        game = self._game(game_id)
        key = (role_id, agent_type)
        if key not in game.agent_memories:
            memory_cls = MEMORY_REGISTRY.get(agent_type)
            if memory_cls is None:
                raise DataError(f"Agent类型 {agent_type} 没有注册记忆实现")
            game.agent_memories[key] = memory_cls(
                game_id, role_id, self._role_store(game_id, role_id), game.public_store, game.clock, self.short_term_size
            )
        return game.agent_memories[key]

    def current_round(self, game_id: str) -> int:
        """当前轮次"""
        return self._game(game_id).clock.round

    def next_round(self, game_id: str) -> int:
        """
        进入下一轮：先通知各 Agent 记忆做轮次收尾，再清除公共短期记忆，最后轮次加一。
        :return: 新的轮次
        """
        game = self._game(game_id)
        for memory in game.agent_memories.values():
            memory.on_round_end()
        game.public_store.remove(MemoryTypeEnum.SHORT_TERM)
        game.clock.round += 1
        return game.clock.round

    # ---------------- 系统写入 ----------------

    def add_role_memory(
        self,
        game_id: str,
        role_id: str,
        content: str,
        category: MemoryCategoryEnum = MemoryCategoryEnum.NOTE,
        metadata: dict[str, Any] | None = None,
        source: str = SYSTEM_SOURCE,
    ) -> MemoryItem:
        """向某个角色写入长期私有记忆，该角色的所有 Agent 可见"""
        item = self._game(game_id).clock.new_item(
            content, MemoryTypeEnum.LONG_TERM, VisibilityEnum.PRIVATE, category, source, metadata
        )
        self._role_store(game_id, role_id).add(item)
        return item

    def publish(
        self,
        game_id: str,
        content: str,
        category: MemoryCategoryEnum = MemoryCategoryEnum.ANNOUNCEMENT,
        metadata: dict[str, Any] | None = None,
        source: str = SYSTEM_SOURCE,
        memory_type: MemoryTypeEnum = MemoryTypeEnum.LONG_TERM,
    ) -> MemoryItem:
        """以系统或 DM 身份写入公共记忆；角色自己的发言应通过其记忆实例的 publish 写入"""
        game = self._game(game_id)
        item = game.clock.new_item(content, memory_type, VisibilityEnum.PUBLIC, category, source, metadata)
        game.public_store.add(item)
        return item

    def record_private_chat(self, game_id: str, sender: str, receiver: str, content: str) -> None:
        """记录一条私聊消息，同时写入双方的长期私有记忆，metadata 中的 partner 为各自的对方"""
        for owner, partner in ((sender, receiver), (receiver, sender)):
            self.add_role_memory(game_id, owner, content, MemoryCategoryEnum.PRIVATE_CHAT, {"partner": partner}, sender)

    def load_character(self, game_id: str, character: Character, role_id: str | None = None) -> str:
        """
        注册角色并写入其身份信息，剧本章节通过 add_story 随游戏进度解锁。
        :param role_id: 角色ID，默认使用角色名
        :return: 角色ID
        """
        role_id = role_id or character.name
        if not role_id:
            raise DataError("角色缺少名称，无法作为角色ID")
        self.register_role(game_id, role_id)
        identity = [
            f"你扮演的角色是{character.name}",
            f"性别：{character.gender}" if character.gender else "",
            f"年龄：{character.age}" if character.age is not None else "",
            f"职业：{character.profession}" if character.profession else "",
            f"背景：{character.background}" if character.background else "",
            "你是本案的凶手" if character.is_murderer else "",
        ]
        self.add_role_memory(game_id, role_id, "；".join(s for s in identity if s), MemoryCategoryEnum.IDENTITY)
        return role_id

    def add_story(self, game_id: str, role_id: str, story: Story) -> MemoryItem:
        """解锁角色的一章剧本"""
        return self.add_role_memory(
            game_id, role_id, story.content or "", MemoryCategoryEnum.SCRIPT,
            {"chapter": story.chapter, "is_end": bool(story.is_end)},
        )

    def add_evidence(self, game_id: str, evidence: Evidence, role_id: str | None = None) -> MemoryItem:
        """
        发放证据：公开证据写入公共记忆；否则写入搜到该证据的角色的私有记忆。
        同一条公开证据可能被多个角色各自读取，带ID的公开证据只写入一次，重复写入时返回已有的记忆。
        :param role_id: 获得证据的角色，非公开证据必须提供
        """
        metadata = {"name": evidence.name, "chapter": evidence.chapter, "evidence_id": evidence.id}
        if evidence.is_public:
            if evidence.id is not None:
                existing = self._game(game_id).public_store.query(
                    filters={"category": MemoryCategoryEnum.EVIDENCE, "evidence_id": evidence.id})
                if existing:
                    return existing[0]
            return self.publish(game_id, evidence.content or "", MemoryCategoryEnum.EVIDENCE, metadata)
        if role_id is None:
            raise DataError(f"非公开证据 {evidence.name} 需要指定获得证据的角色")
        return self.add_role_memory(game_id, role_id, evidence.content or "", MemoryCategoryEnum.EVIDENCE, metadata)

    # ---------------- 持久化 ----------------

    def save(self, game_id: str, path: str | Path) -> None:
        """把一局游戏的记忆保存为 JSON 文件"""
        game = self._game(game_id)
        data = {
            "game_id": game_id,
            "round": game.clock.round,
            "seq": game.clock.seq,
            "public": game.public_store.to_list(),
            "roles": {role_id: store.to_list() for role_id, store in game.role_stores.items()},
            "agents": [
                {"role_id": role_id, "agent_type": agent_type.value, "data": memory.to_dict()}
                for (role_id, agent_type), memory in game.agent_memories.items()
            ],
        }
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def load(self, path: str | Path) -> str:
        """从 JSON 文件恢复一局游戏的记忆，已存在同ID的游戏时覆盖；返回游戏ID"""
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        game_id = data["game_id"]
        self.remove_game(game_id)
        self.create_game(game_id)
        game = self._games[game_id]
        game.clock.round, game.clock.seq = data["round"], data["seq"]
        game.public_store.load_list(data["public"])
        for role_id, items in data["roles"].items():
            self.register_role(game_id, role_id)
            game.role_stores[role_id].load_list(items)
        for agent in data["agents"]:
            memory = self.get_agent_memory(game_id, agent["role_id"], AgentTypeEnum(agent["agent_type"]))
            memory.load_dict(agent["data"])
        return game_id

    # ---------------- 内部方法 ----------------

    def _game(self, game_id: str) -> _GameMemory:
        game = self._games.get(game_id)
        if game is None:
            raise DataError(f"游戏 {game_id} 的记忆不存在，请先调用 create_game")
        return game

    def _role_store(self, game_id: str, role_id: str) -> MemoryStore:
        """角色必须先注册，避免角色ID拼写错误时悄悄创建出新的记忆空间"""
        store = self._game(game_id).role_stores.get(role_id)
        if store is None:
            raise DataError(f"游戏 {game_id} 中角色 {role_id} 未注册")
        return store
