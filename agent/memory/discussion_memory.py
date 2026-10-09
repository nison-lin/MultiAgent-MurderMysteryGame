"""讨论 Agent 的记忆"""

from collections import defaultdict

from agent.memory.base_memory import BaseMemory, register_memory
from agent.memory.memory_enum import AgentTypeEnum, MemoryCategoryEnum, MemoryTypeEnum, VisibilityEnum
from agent.memory.memory_store import MemoryItem


@register_memory
class DiscussionMemory(BaseMemory):
    """
    讨论 Agent 的记忆，按轮次组织公共发言。
    关注：本轮及最近几轮的公开发言、他人的观点、当前讨论焦点。
    讨论焦点存为短期记忆，轮次结束时转存为长期记忆，作为该轮讨论的回顾。
    """

    AGENT_TYPE = AgentTypeEnum.DISCUSSION
    # 摘要中展示最近几轮的发言（含当前轮）
    SUMMARY_ROUNDS = 2

    def add_speech(self, content: str) -> MemoryItem:
        """记录本角色的公开发言，所有角色可见"""
        return self.publish(content, MemoryCategoryEnum.SPEECH)

    def get_speeches(self, round: int | None = None, speaker: str | None = None) -> list[MemoryItem]:
        """读取公开发言，可按轮次和发言者过滤"""
        filters: dict = {"category": MemoryCategoryEnum.SPEECH}
        if round is not None:
            filters["round"] = round
        if speaker is not None:
            filters["source"] = speaker
        return self.get_memory(filters=filters)

    def get_speeches_by_round(self) -> dict[int, list[MemoryItem]]:
        """按轮次分组的全部公开发言"""
        grouped: dict[int, list[MemoryItem]] = defaultdict(list)
        for item in self.get_speeches():
            grouped[item.round].append(item)
        return dict(grouped)

    def note_opinion(self, speaker: str, opinion: str) -> MemoryItem:
        """记录对某位角色观点的理解（如"张三认为李四是凶手"），仅自己可见"""
        return self.add_memory(opinion, metadata={"speaker": speaker}, category=MemoryCategoryEnum.OPINION, source=speaker)

    def set_focus(self, focus: str) -> MemoryItem:
        """设置当前讨论焦点，覆盖之前的焦点"""
        self._short_term.remove(filters={"category": MemoryCategoryEnum.FOCUS})
        return self.add_memory(focus, MemoryTypeEnum.SHORT_TERM, category=MemoryCategoryEnum.FOCUS)

    def get_focus(self) -> str | None:
        """当前讨论焦点"""
        items = self._short_term.query(filters={"category": MemoryCategoryEnum.FOCUS})
        return items[-1].content if items else None

    def on_round_end(self) -> None:
        """把本轮的讨论焦点转存为长期记忆后再清空短期记忆"""
        focus = self.get_focus()
        if focus:
            self.add_memory(focus, category=MemoryCategoryEnum.FOCUS)
        super().on_round_end()

    def _focus_sections(self) -> list[str]:
        focus = self.get_focus()
        sections = [f"【当前讨论焦点】\n- {focus}" if focus else ""]

        # 最近几轮的发言按轮次分段，更早的轮次只保留讨论焦点回顾
        first_round = max(1, self.current_round - self.SUMMARY_ROUNDS + 1)
        for round in range(first_round, self.current_round + 1):
            speeches = self.get_speeches(round=round)[-self.SUMMARY_LIMIT:]
            sections.append(self._section(f"第{round}轮发言", speeches, lambda i: f"{i.source}：{i.content}"))

        history = self._role_store.query(filters={"category": MemoryCategoryEnum.FOCUS})
        sections.append(self._section("往轮讨论焦点", history[-self.SUMMARY_LIMIT:], lambda i: f"第{i.round}轮：{i.content}"))

        # 每位角色只展示最新的观点
        latest: dict[str, MemoryItem] = {}
        for item in self._role_store.query(filters={"category": MemoryCategoryEnum.OPINION}):
            latest[item.metadata.get("speaker", item.source)] = item
        sections.append(self._section("他人观点", latest.values(), lambda i: f"{i.source}：{i.content}"))

        sections.append(self._section("系统公告", self._recent(category=MemoryCategoryEnum.ANNOUNCEMENT)))
        sections.append(self._section("当前轮次笔记", self._short_term.query(
            filters={"category": [c for c in MemoryCategoryEnum if c != MemoryCategoryEnum.FOCUS]})))
        return sections
