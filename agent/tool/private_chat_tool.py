"""私聊 Agent 的工具"""

from typing import Annotated, List

from agent.memory.memory_enum import MemoryCategoryEnum
from agent.memory.memory_store import MemoryItem
from agent.memory.private_chat_memory import PrivateChatMemory
from agent.tool.base_tool import BaseTool, create_tool
from agent.tool.memory_tool import build_memory_tools, format_items, require_text


def build_private_chat_tools(memory: PrivateChatMemory) -> List[BaseTool]:
    """
    构建私聊 Agent 的工具集。
    正在与某人私聊时，工具只能读取与该对象的私聊记录，避免把与他人的私聊内容带入当前对话；
    没有私聊对象时（如判断要不要发起私聊），可以查阅与所有人的私聊记录。
    """

    def visible(item: MemoryItem) -> bool:
        partner = memory.current_partner
        if partner is None or item.category != MemoryCategoryEnum.PRIVATE_CHAT:
            return True
        return item.metadata.get("partner") == partner

    def note_partner(
        partner: Annotated[str, "私聊对象的角色名"],
        note: Annotated[str, "笔记内容"],
    ) -> str:
        partner, note = require_text(partner, "partner"), require_text(note, "note")
        memory.note_partner(partner, note)
        return f"已记录关于{partner}的笔记"

    def get_conversation(
        partner: Annotated[str, "私聊对象的角色名"],
        limit: Annotated[int, "最多返回最近的多少条，默认20"] = 20,
    ) -> str:
        partner = require_text(partner, "partner")
        if memory.current_partner is not None and partner != memory.current_partner:
            return f"你正在与{memory.current_partner}私聊，不能查看与{partner}的私聊记录"
        return format_items(memory.get_conversation(partner, max(1, int(limit))), f"你与{partner}还没有私聊过")

    def list_partners() -> str:
        partners = memory.partners()
        return "私聊过的角色：" + "、".join(partners) if partners else "你还没有与任何人私聊过"

    return build_memory_tools(memory, visible) + [
        create_tool(
            "note_partner",
            "记录关于某个私聊对象的笔记，如达成的约定、从对方处得到的信息、对其可信度的判断，仅自己可见",
            note_partner,
        ),
        create_tool("get_conversation", "查看与某个角色的私聊记录", get_conversation),
        create_tool("list_partners", "列出私聊过的所有角色", list_partners),
    ]
