"""记忆基类"""

from typing import Any, Callable, Iterable

from agent.memory.memory_enum import AgentTypeEnum, MemoryCategoryEnum, MemoryTypeEnum, VisibilityEnum
from agent.memory.memory_store import GameClock, MemoryFilters, MemoryItem, MemoryStore

# Agent类型 -> 记忆实现，由 register_memory 装饰器填充，MemoryManager 据此创建记忆
MEMORY_REGISTRY: dict[AgentTypeEnum, type["BaseMemory"]] = {}


def register_memory(cls: type["BaseMemory"]) -> type["BaseMemory"]:
    """注册记忆实现，新增 Agent 类型时在子类上使用该装饰器即可"""
    MEMORY_REGISTRY[cls.AGENT_TYPE] = cls
    return cls


class BaseMemory:
    """
    单个 Agent 的记忆，按时效与可见性分为三处存储：
        短期私有      本实例独有，轮次结束时清除，有条数上限
        长期私有      同一角色的所有 Agent 共享（剧本、身份、证据、私聊等），其他角色无法访问
        公共          同一局游戏共享，只能通过 add_memory / publish 写入，发布者固定为本角色
    实例只持有本角色的存储与公共存储的引用，从结构上保证角色之间的记忆隔离。

    子类通常只需要：
        1. 声明 AGENT_TYPE 并使用 @register_memory 注册
        2. 提供该类型专用的读写方法
        3. 重写 _focus_sections() 决定摘要内容，有结构化数据时重写 to_dict() / load_dict() / clear_memory()
    """

    AGENT_TYPE: AgentTypeEnum
    # 摘要中每个分段最多展示的条数
    SUMMARY_LIMIT = 10

    def __init__(
        self,
        game_id: str,
        role_id: str,
        role_store: MemoryStore,
        public_store: MemoryStore,
        clock: GameClock,
        short_term_size: int = 50,
    ):
        """
        :param game_id: 游戏ID
        :param role_id: 角色ID（玩家角色名或 DM），也是本角色发布记忆时的来源
        :param role_store: 本角色的长期私有存储
        :param public_store: 本局游戏的公共存储
        :param clock: 本局游戏的全局时钟
        :param short_term_size: 短期记忆条数上限
        """
        self.game_id = game_id
        self.role_id = role_id
        self.memory_id = f"{game_id}:{role_id}:{self.AGENT_TYPE.value}"
        self._short_term = MemoryStore(max_size=short_term_size)
        self._role_store = role_store
        self._public_store = public_store
        self._clock = clock

    @property
    def current_round(self) -> int:
        """当前轮次"""
        return self._clock.round

    # ---------------- 通用接口 ----------------

    def add_memory(
        self,
        content: str,
        memory_type: MemoryTypeEnum = MemoryTypeEnum.LONG_TERM,
        metadata: dict[str, Any] | None = None,
        visibility: VisibilityEnum = VisibilityEnum.PRIVATE,
        category: MemoryCategoryEnum = MemoryCategoryEnum.NOTE,
        source: str | None = None,
    ) -> MemoryItem:
        """
        写入一条记忆。
        :param source: 信息来源，默认为本角色；公共记忆的来源固定为本角色，防止冒充他人发言
        """
        if visibility == VisibilityEnum.PUBLIC or source is None:
            source = self.role_id
        item = self._clock.new_item(content, memory_type, visibility, category, source, metadata)
        self._store_for(memory_type, visibility).add(item)
        return item

    def publish(
        self,
        content: str,
        category: MemoryCategoryEnum = MemoryCategoryEnum.SPEECH,
        metadata: dict[str, Any] | None = None,
    ) -> MemoryItem:
        """以本角色身份发布一条长期公共记忆"""
        return self.add_memory(content, MemoryTypeEnum.LONG_TERM, metadata, VisibilityEnum.PUBLIC, category)

    def get_memory(
        self,
        memory_type: MemoryTypeEnum | None = None,
        filters: MemoryFilters | None = None,
        limit: int | None = None,
    ) -> list[MemoryItem]:
        """
        读取本角色可见的记忆（短期私有 + 长期私有 + 公共），按产生顺序排列。
        :param filters: 过滤条件，如 {"category": MemoryCategoryEnum.SPEECH, "round": 2}；
                        可用 {"visibility": VisibilityEnum.PUBLIC} 只看公共记忆
        :param limit: 只返回最近的若干条
        """
        items = [
            item
            for store in (self._short_term, self._role_store, self._public_store)
            for item in store.query(memory_type, filters)
        ]
        items.sort(key=lambda item: item.seq)
        return items[-limit:] if limit is not None and limit > 0 else items

    def clear_memory(self, memory_type: MemoryTypeEnum | None = None, filters: MemoryFilters | None = None) -> int:
        """
        清除本角色的私有记忆，返回清除条数；公共记忆不受影响，只能由 MemoryManager 管理。
        注意长期私有记忆由同一角色的所有 Agent 共享，清除时会一并影响它们。
        """
        removed = 0
        if memory_type in (None, MemoryTypeEnum.SHORT_TERM):
            removed += self._short_term.remove(filters=filters)
        if memory_type in (None, MemoryTypeEnum.LONG_TERM):
            removed += self._role_store.remove(filters=filters)
        return removed

    def summarize(self, include_script: bool = False) -> str:
        """
        生成供 Agent 决策使用的记忆摘要文本。
        :param include_script: 是否包含剧本全文；剧本较长，已放入系统提示词时无需重复
        """
        sections = self._core_sections(include_script) + self._focus_sections()
        return "\n\n".join(s for s in sections if s) or "暂无记忆"

    # ---------------- 可重写的钩子 ----------------

    def on_round_end(self) -> None:
        """轮次结束时由 MemoryManager 调用（轮次递增前），默认清空短期记忆；子类可先把需要保留的内容转存为长期记忆"""
        self._short_term.remove()

    def _focus_sections(self) -> list[str]:
        """该 Agent 类型关注的摘要分段，默认为短期记忆与系统公告"""
        return [
            self._section("当前轮次记忆", self._short_term.query()),
            self._section("系统公告", self._recent(category=MemoryCategoryEnum.ANNOUNCEMENT)),
        ]

    def to_dict(self) -> dict[str, Any]:
        """序列化本实例独有的数据（共享存储由 MemoryManager 统一保存）"""
        return {"short_term": self._short_term.to_list()}

    def load_dict(self, data: dict[str, Any]) -> None:
        """从 to_dict 的结果还原"""
        self._short_term.load_list(data.get("short_term", []))

    # ---------------- 内部方法 ----------------

    def _store_for(self, memory_type: MemoryTypeEnum, visibility: VisibilityEnum) -> MemoryStore:
        """根据时效与可见性选择存储"""
        if visibility == VisibilityEnum.PUBLIC:
            return self._public_store
        if memory_type == MemoryTypeEnum.SHORT_TERM:
            return self._short_term
        return self._role_store

    def _recent(self, limit: int | None = None, **filters: Any) -> list[MemoryItem]:
        """按条件读取最近的若干条记忆，默认条数为 SUMMARY_LIMIT"""
        return self.get_memory(filters=filters, limit=limit or self.SUMMARY_LIMIT)

    def _core_sections(self, include_script: bool) -> list[str]:
        """所有 Agent 类型共有的角色核心信息：身份、剧本、持有的证据"""
        identity = self._role_store.query(filters={"category": MemoryCategoryEnum.IDENTITY})
        sections = [self._section("角色身份", identity, lambda i: i.content)]
        if include_script:
            scripts = self._role_store.query(filters={"category": MemoryCategoryEnum.SCRIPT})
            sections.append(self._section("剧本", scripts, lambda i: f"第{i.metadata.get('chapter', '?')}章：{i.content}"))
        sections.append(self._section("已知证据", self._recent(category=MemoryCategoryEnum.EVIDENCE), self._format_evidence))
        return sections

    @staticmethod
    def _section(
        title: str,
        items: Iterable[MemoryItem],
        formatter: Callable[[MemoryItem], str] | None = None,
    ) -> str:
        """把一组记忆格式化为带标题的分段，没有内容时返回空字符串"""
        formatter = formatter or BaseMemory._format_item
        lines = [f"- {formatter(item)}" for item in items]
        return f"【{title}】\n" + "\n".join(lines) if lines else ""

    @staticmethod
    def _format_item(item: MemoryItem) -> str:
        """默认的单条记忆格式：[第N轮] 来源：内容"""
        return f"[第{item.round}轮] {item.source}：{item.content}"

    @staticmethod
    def _format_evidence(item: MemoryItem) -> str:
        """证据格式：名称（公开/私有）：内容"""
        name = item.metadata.get("name", "未命名证据")
        scope = "公开" if item.visibility == VisibilityEnum.PUBLIC else "私有"
        return f"{name}（{scope}）：{item.content}"
