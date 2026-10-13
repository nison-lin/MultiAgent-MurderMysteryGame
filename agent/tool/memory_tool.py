"""所有子 Agent 共用的记忆查询工具"""

from typing import Any, Callable, List

from agent.memory.base_memory import BaseMemory
from agent.memory.memory_enum import MemoryCategoryEnum, VisibilityEnum
from agent.memory.memory_store import MemoryItem
from agent.tool.base_tool import BaseTool
from error.errors import UserInputError

# 单次查询最多返回的条数
MAX_SEARCH_LIMIT = 50

# 记忆过滤器：返回 False 的条目不会出现在查询结果中
ItemFilter = Callable[[MemoryItem], bool]


def format_item(item: MemoryItem) -> str:
    """工具返回结果中单条记忆的格式：[第N轮] 来源（类别）：内容"""
    if item.category == MemoryCategoryEnum.EVIDENCE:
        scope = "公开" if item.visibility == VisibilityEnum.PUBLIC else "私有"
        return f"[第{item.round}轮] 证据「{item.metadata.get('name', '未命名证据')}」（{scope}）：{item.content}"
    return f"[第{item.round}轮] {item.source}（{item.category.value}）：{item.content}"


def format_items(items: List[MemoryItem], empty: str = "没有找到相关记忆") -> str:
    """把一组记忆格式化为工具返回的文本"""
    return "\n".join(format_item(item) for item in items) if items else empty


def require_text(value: Any, field: str) -> str:
    """校验工具的文本参数非空"""
    text = str(value or "").strip()
    if not text:
        raise UserInputError(f"参数 {field} 不能为空")
    return text


def build_memory_tools(memory: BaseMemory, item_filter: ItemFilter | None = None) -> List[BaseTool]:
    """
    构建记忆查询工具，只能读取该记忆实例可见的内容。
    :param item_filter: 额外的过滤条件，如私聊 Agent 用它屏蔽与其他角色的私聊记录
    """

    def search_memory(
        keyword: str = "",
        category: str | None = None,
        source: str | None = None,
        round: int | None = None,
        limit: int = 20,
    ) -> str:
        filters: dict[str, Any] = {}
        if category:
            filters["category"] = MemoryCategoryEnum(category)
        if source:
            filters["source"] = source
        if round is not None:
            filters["round"] = int(round)
        items = [
            item for item in memory.get_memory(filters=filters)
            if (not keyword or keyword in item.content) and (item_filter is None or item_filter(item))
        ]
        limit = max(1, min(int(limit), MAX_SEARCH_LIMIT))
        return format_items(items[-limit:])

    return [
        BaseTool(
            name="search_memory",
            description="检索你记得的信息（剧本、证据、发言、私聊、公告、笔记等），记忆摘要中被省略的内容可以通过它查到",
            func=search_memory,
            parameters={
                "type": "object",
                "properties": {
                    "keyword": {"type": "string", "description": "内容中包含的关键词，为空表示不限"},
                    "category": {
                        "type": "string",
                        "enum": [c.value for c in MemoryCategoryEnum],
                        "description": "记忆类别，为空表示不限",
                    },
                    "source": {"type": "string", "description": "信息来源，如某个角色名或“系统”，为空表示不限"},
                    "round": {"type": "integer", "description": "轮次，为空表示不限"},
                    "limit": {"type": "integer", "description": f"最多返回最近的多少条，默认20，最大{MAX_SEARCH_LIMIT}"},
                },
            },
        ),
    ]
