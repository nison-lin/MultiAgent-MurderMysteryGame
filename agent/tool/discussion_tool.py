"""讨论 Agent 的工具"""

from typing import List

from agent.memory.discussion_memory import DiscussionMemory
from agent.tool.base_tool import BaseTool
from agent.tool.memory_tool import build_memory_tools, format_items, require_text


def build_discussion_tools(memory: DiscussionMemory) -> List[BaseTool]:
    """构建讨论 Agent 的工具集"""

    def note_opinion(speaker: str, opinion: str) -> str:
        speaker, opinion = require_text(speaker, "speaker"), require_text(opinion, "opinion")
        memory.note_opinion(speaker, opinion)
        return f"已记录{speaker}的观点"

    def set_focus(focus: str) -> str:
        memory.set_focus(require_text(focus, "focus"))
        return "已更新当前讨论焦点"

    def get_speeches(round: int | None = None, speaker: str | None = None) -> str:
        speeches = memory.get_speeches(int(round) if round is not None else None, speaker or None)
        return format_items(speeches, "没有符合条件的发言")

    return build_memory_tools(memory) + [
        BaseTool(
            name="note_opinion",
            description="记录对某位角色观点的理解，如“张三认为李四是凶手，依据是……”，仅自己可见；同一角色以最新的观点为准",
            func=note_opinion,
            parameters={
                "type": "object",
                "properties": {
                    "speaker": {"type": "string", "description": "持有该观点的角色名"},
                    "opinion": {"type": "string", "description": "观点内容"},
                },
                "required": ["speaker", "opinion"],
            },
        ),
        BaseTool(
            name="set_focus",
            description="设置当前讨论焦点（大家正在争论的问题），会覆盖之前的焦点",
            func=set_focus,
            parameters={
                "type": "object",
                "properties": {"focus": {"type": "string", "description": "讨论焦点"}},
                "required": ["focus"],
            },
        ),
        BaseTool(
            name="get_speeches",
            description="查看公开发言，可按轮次和发言者过滤，用于查阅摘要中没有展示的早期发言",
            func=get_speeches,
            parameters={
                "type": "object",
                "properties": {
                    "round": {"type": "integer", "description": "轮次，为空表示所有轮次"},
                    "speaker": {"type": "string", "description": "发言者角色名，为空表示所有人"},
                },
            },
        ),
    ]
