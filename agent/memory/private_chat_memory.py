"""私聊 Agent 的记忆"""

from typing import Any

from agent.memory.base_memory import BaseMemory, register_memory
from agent.memory.memory_enum import AgentTypeEnum, MemoryCategoryEnum, MemoryTypeEnum
from agent.memory.memory_store import MemoryItem


@register_memory
class PrivateChatMemory(BaseMemory):
    """
    私聊 Agent 的记忆，按对话对象隔离。
    私聊消息由 MemoryManager.record_private_chat 同时写入双方的长期私有记忆，metadata 中记录 partner（对方角色）。
    摘要只包含当前对话对象的聊天记录与笔记，避免把与他人的私聊内容带入当前对话。
    """

    AGENT_TYPE = AgentTypeEnum.PRIVATE_CHAT
    # 摘要中展示与当前对象最近的聊天条数
    CHAT_LIMIT = 20

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.current_partner: str | None = None

    def start_chat(self, partner: str) -> None:
        """开始与某个角色私聊，之后的摘要都围绕该对象；切换对象时清空上一段对话的短期记忆"""
        if partner != self.current_partner:
            self._short_term.remove()
        self.current_partner = partner

    def end_chat(self) -> None:
        """结束当前私聊"""
        self.current_partner = None
        self._short_term.remove()

    def get_conversation(self, partner: str, limit: int | None = None) -> list[MemoryItem]:
        """与某个角色的私聊记录"""
        filters = {"category": MemoryCategoryEnum.PRIVATE_CHAT, "partner": partner}
        return self.get_memory(MemoryTypeEnum.LONG_TERM, filters, limit)

    def partners(self) -> list[str]:
        """私聊过的角色，按首次私聊顺序"""
        items = self._role_store.query(filters={"category": MemoryCategoryEnum.PRIVATE_CHAT})
        return list(dict.fromkeys(item.metadata["partner"] for item in items))

    def note_partner(self, partner: str, note: str) -> MemoryItem:
        """记录关于某个私聊对象的笔记（如达成的约定、对其的判断），仅自己可见"""
        return self.add_memory(note, metadata={"partner": partner}, category=MemoryCategoryEnum.NOTE)

    def to_dict(self) -> dict[str, Any]:
        return {**super().to_dict(), "current_partner": self.current_partner}

    def load_dict(self, data: dict[str, Any]) -> None:
        super().load_dict(data)
        self.current_partner = data.get("current_partner")

    def _focus_sections(self) -> list[str]:
        partner = self.current_partner
        if partner is None:
            others = "、".join(self.partners())
            return ["【私聊】\n- 当前没有私聊对象" + (f"，私聊过：{others}" if others else "")]
        notes = self._role_store.query(filters={"category": MemoryCategoryEnum.NOTE, "partner": partner})
        return [
            f"【当前私聊对象】\n- {partner}",
            self._section(f"关于{partner}的笔记", notes[-self.SUMMARY_LIMIT:], lambda i: i.content),
            self._section(f"与{partner}的私聊记录", self.get_conversation(partner, self.CHAT_LIMIT)),
            self._section("当前对话记忆", self._short_term.query()),
        ]
