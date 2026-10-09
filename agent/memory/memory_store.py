"""记忆条目与存储容器"""

import copy
import uuid
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime
from typing import Any

from agent.memory.memory_enum import MemoryCategoryEnum, MemoryTypeEnum, VisibilityEnum

# 记忆过滤条件：键为 MemoryItem 的字段名或 metadata 中的键，值为单个值或候选值列表
MemoryFilters = dict[str, Any]


@dataclass
class MemoryItem:
    """单条记忆"""
    content: str
    memory_type: MemoryTypeEnum
    visibility: VisibilityEnum
    category: MemoryCategoryEnum
    source: str   # 信息来源：角色ID、"系统"等
    round: int    # 产生该记忆的轮次
    seq: int      # 同一局游戏内的全局序号，跨存储合并时按此排序
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    metadata: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: uuid.uuid4().hex)

    def matches(self, memory_type: MemoryTypeEnum | None = None, filters: MemoryFilters | None = None) -> bool:
        """判断是否满足过滤条件。字段名优先匹配条目字段，否则匹配 metadata；值为列表等容器时表示任一匹配"""
        if memory_type is not None and self.memory_type != memory_type:
            return False
        for key, expected in (filters or {}).items():
            actual = getattr(self, key) if key in _ITEM_FIELDS else self.metadata.get(key)
            if isinstance(expected, (list, tuple, set, frozenset)):
                if actual not in expected:
                    return False
            elif actual != expected:
                return False
        return True

    def to_dict(self) -> dict[str, Any]:
        """转为可JSON序列化的字典"""
        data = asdict(self)
        for key in ("memory_type", "visibility", "category"):
            data[key] = data[key].value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MemoryItem":
        """从 to_dict 的结果还原"""
        return cls(**{
            **data,
            "memory_type": MemoryTypeEnum(data["memory_type"]),
            "visibility": VisibilityEnum(data["visibility"]),
            "category": MemoryCategoryEnum(data["category"]),
        })


_ITEM_FIELDS = frozenset(f.name for f in fields(MemoryItem))


@dataclass
class GameClock:
    """一局游戏的全局时钟：当前轮次与记忆序号，由同一局的所有存储共享"""
    round: int = 1
    seq: int = 0

    def new_item(
        self,
        content: str,
        memory_type: MemoryTypeEnum,
        visibility: VisibilityEnum,
        category: MemoryCategoryEnum,
        source: str,
        metadata: dict[str, Any] | None = None,
    ) -> MemoryItem:
        """创建记忆条目，自动填充当前轮次与序号"""
        self.seq += 1
        return MemoryItem(
            content=content,
            memory_type=memory_type,
            visibility=visibility,
            category=category,
            source=source,
            round=self.round,
            seq=self.seq,
            metadata=dict(metadata or {}),
        )


class MemoryStore:
    """
    记忆容器，只负责存取，不关心归属。
    写入与读取都做深拷贝，外部拿到的条目被修改也不会影响内部数据。
    """

    def __init__(self, max_size: int | None = None):
        """:param max_size: 最多保留的条数，超出时丢弃最早的条目；为空表示不限制"""
        self.max_size = max_size
        self._items: list[MemoryItem] = []

    def __len__(self) -> int:
        return len(self._items)

    def add(self, item: MemoryItem) -> None:
        """写入一条记忆"""
        self._items.append(copy.deepcopy(item))
        if self.max_size is not None and len(self._items) > self.max_size:
            del self._items[: len(self._items) - self.max_size]

    def query(self, memory_type: MemoryTypeEnum | None = None, filters: MemoryFilters | None = None) -> list[MemoryItem]:
        """按条件读取，返回副本"""
        return [copy.deepcopy(item) for item in self._items if item.matches(memory_type, filters)]

    def remove(self, memory_type: MemoryTypeEnum | None = None, filters: MemoryFilters | None = None) -> int:
        """按条件删除，返回删除条数；不传条件时清空"""
        kept = [item for item in self._items if not item.matches(memory_type, filters)]
        removed = len(self._items) - len(kept)
        self._items = kept
        return removed

    def to_list(self) -> list[dict[str, Any]]:
        """序列化全部条目"""
        return [item.to_dict() for item in self._items]

    def load_list(self, data: list[dict[str, Any]]) -> None:
        """用序列化数据覆盖当前内容"""
        self._items = []
        for item in data:
            self.add(MemoryItem.from_dict(item))
