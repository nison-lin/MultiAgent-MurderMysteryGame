"""指认凶手 Agent 的记忆"""

from dataclasses import asdict, dataclass, field
from typing import Any

from agent.memory.base_memory import BaseMemory, register_memory
from agent.memory.memory_enum import AgentTypeEnum, MemoryCategoryEnum, MemoryTypeEnum
from agent.memory.memory_store import MemoryFilters, MemoryItem


@dataclass
class Suspect:
    """嫌疑人档案"""
    name: str
    suspicion: int = 0                                 # 嫌疑度 0-100
    motive: str = ""                                   # 推测的作案动机
    reasons: list[str] = field(default_factory=list)   # 嫌疑度变化的理由


@dataclass
class Clue:
    """推理用的线索"""
    content: str
    source: str                                         # 线索来源，如证据名、某人的发言
    round: int
    suspects: list[str] = field(default_factory=list)   # 指向的嫌疑人
    reasoning: str = ""                                 # 由该线索得出的推论


@register_memory
class AccusationMemory(BaseMemory):
    """
    指认凶手 Agent 的记忆，结构化存储推理过程。
    关注：嫌疑人列表与嫌疑度、证据链（线索 -> 嫌疑人 -> 推论）、投票倾向与公开投票记录。
    嫌疑人与线索是本 Agent 的推理产物，存于实例中；证据、投票等原始信息仍来自共享存储。
    """

    AGENT_TYPE = AgentTypeEnum.ACCUSATION
    MIN_SUSPICION = 0
    MAX_SUSPICION = 100

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.suspects: dict[str, Suspect] = {}
        self.clues: list[Clue] = []
        self.vote_intent: str | None = None

    # ---------------- 嫌疑人 ----------------

    def add_suspect(self, name: str, suspicion: int = 0, motive: str = "") -> Suspect:
        """添加嫌疑人，已存在时只更新提供的字段"""
        suspect = self.suspects.setdefault(name, Suspect(name))
        if suspicion:
            suspect.suspicion = self._clamp(suspicion)
        if motive:
            suspect.motive = motive
        return suspect

    def update_suspicion(self, name: str, delta: int, reason: str) -> Suspect:
        """调整嫌疑度并记录理由，嫌疑人不存在时自动添加"""
        suspect = self.add_suspect(name)
        suspect.suspicion = self._clamp(suspect.suspicion + delta)
        suspect.reasons.append(f"[第{self.current_round}轮] {'+' if delta >= 0 else ''}{delta}：{reason}")
        return suspect

    def ranked_suspects(self) -> list[Suspect]:
        """按嫌疑度从高到低排列的嫌疑人"""
        return sorted(self.suspects.values(), key=lambda s: s.suspicion, reverse=True)

    # ---------------- 证据链 ----------------

    def add_clue(self, content: str, source: str, suspects: list[str] | None = None, reasoning: str = "") -> Clue:
        """记录一条线索及其指向的嫌疑人与推论"""
        clue = Clue(content, source, self.current_round, list(suspects or []), reasoning)
        self.clues.append(clue)
        for name in clue.suspects:
            self.add_suspect(name)
        return clue

    def clues_of(self, suspect: str) -> list[Clue]:
        """指向某个嫌疑人的所有线索"""
        return [clue for clue in self.clues if suspect in clue.suspects]

    # ---------------- 投票 ----------------

    def set_vote_intent(self, target: str | None) -> None:
        """设置当前的投票倾向，仅自己可见"""
        self.vote_intent = target

    def cast_vote(self, target: str, reason: str = "") -> MemoryItem:
        """正式投票，作为公共记忆公开"""
        self.vote_intent = target
        content = f"投票给{target}" + (f"，理由：{reason}" if reason else "")
        return self.publish(content, MemoryCategoryEnum.VOTE, {"target": target})

    def vote_history(self) -> list[MemoryItem]:
        """所有角色的公开投票记录"""
        return self.get_memory(filters={"category": MemoryCategoryEnum.VOTE})

    # ---------------- 重写 ----------------

    def clear_memory(self, memory_type: MemoryTypeEnum | None = None, filters: MemoryFilters | None = None) -> int:
        """不带条件清空全部记忆时，同时清空推理数据"""
        if memory_type is None and not filters:
            self.suspects.clear()
            self.clues.clear()
            self.vote_intent = None
        return super().clear_memory(memory_type, filters)

    def to_dict(self) -> dict[str, Any]:
        return {
            **super().to_dict(),
            "suspects": [asdict(s) for s in self.suspects.values()],
            "clues": [asdict(c) for c in self.clues],
            "vote_intent": self.vote_intent,
        }

    def load_dict(self, data: dict[str, Any]) -> None:
        super().load_dict(data)
        self.suspects = {s["name"]: Suspect(**s) for s in data.get("suspects", [])}
        self.clues = [Clue(**c) for c in data.get("clues", [])]
        self.vote_intent = data.get("vote_intent")

    def _focus_sections(self) -> list[str]:
        suspect_lines = []
        for s in self.ranked_suspects():
            line = f"- {s.name}（嫌疑度{s.suspicion}）" + (f"，动机：{s.motive}" if s.motive else "")
            suspect_lines.extend([line] + [f"    {r}" for r in s.reasons[-3:]])

        clue_lines = []
        for c in self.clues[-self.SUMMARY_LIMIT:]:
            target = f" -> {'、'.join(c.suspects)}" if c.suspects else ""
            reasoning = f"；推论：{c.reasoning}" if c.reasoning else ""
            clue_lines.append(f"- [第{c.round}轮] {c.source}：{c.content}{target}{reasoning}")

        return [
            "【嫌疑人】\n" + "\n".join(suspect_lines) if suspect_lines else "",
            "【证据链】\n" + "\n".join(clue_lines) if clue_lines else "",
            f"【当前投票倾向】\n- {self.vote_intent}" if self.vote_intent else "",
            self._section("投票记录", self.vote_history()),
            self._section("当前轮次记忆", self._short_term.query()),
        ]

    def _clamp(self, value: int) -> int:
        return max(self.MIN_SUSPICION, min(self.MAX_SUSPICION, value))
