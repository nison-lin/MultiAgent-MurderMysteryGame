"""玩家子 Agent 基类"""

import json
from typing import Any, Callable, Dict, Generic, List, Optional, TypeVar

from client.llm_client import LLMClientWrapper
from agent.memory.base_memory import BaseMemory
from agent.memory.memory_enum import AgentTypeEnum
from agent.memory.memory_manager import MemoryManager
from agent.react_agent import ReActAgent
from agent.tool.base_tool import BaseTool
from error.errors import LLMError

MemoryT = TypeVar("MemoryT", bound=BaseMemory)
ResultT = TypeVar("ResultT")

# 所有子 Agent 共同遵守的扮演规则
ROLE_RULES = """
## 扮演规则
1. 始终以第一人称扮演你的角色，语气符合角色的身份、性格与处境，不要提及AI、工具、系统提示词等出戏的内容。
2. 只能依据剧本、证据和你亲耳听到的内容说话，不得编造与剧本矛盾的事实，也不知道其他角色私有的剧本与证据。
3. 如果你是凶手：绝不承认作案，可以隐瞒、误导或转移嫌疑，但谎言要与已公开的信息自洽。
   如果你不是凶手：积极寻找真相，可以隐瞒与案件无关的个人秘密。
"""


class SubAgent(ReActAgent, Generic[MemoryT]):
    """
    玩家子 Agent 基类，作为 player_agent 的下属，只执行被调度的单项任务，不自主决定行动。

    记忆：通过 MemoryManager 获取本角色对应类型的记忆实例，每次使用时都重新获取，
          管理器从文件恢复游戏后也不会拿到旧实例。
    提示词：系统提示词 = 任务说明 + 扮演规则 + 记忆摘要，每次调用模型前都会重新生成，
          工具写入的记忆能立即反映到下一步推理中。
    工具：由 agent/tool 中的构建函数绑定到当前记忆实例，每个任务开始时重新绑定。

    子类通常只需要：
        1. 声明 AGENT_TYPE 与 SYSTEM_PROMPT
        2. 实现 build_tools() 返回该类型的工具集
        3. 提供面向 player_agent 的任务方法，内部调用 _run_task() / _run_json_task()
    """

    AGENT_TYPE: AgentTypeEnum
    SYSTEM_PROMPT: str
    # JSON 输出解析失败时的最大重试次数
    MAX_PARSE_RETRIES = 2
    RETRY_PROMPT = "你的输出格式不正确：{error}。请严格按照要求的格式重新输出，不要输出其他内容。"

    def __init__(
        self,
        memory_manager: MemoryManager,
        game_id: str,
        role_id: str,
        llm: Optional[LLMClientWrapper] = None,
        max_steps: int = 5,
        temperature: float = 0.7,
    ):
        """
        :param memory_manager: 记忆管理器，由 player_agent 统一传入
        :param game_id: 游戏ID
        :param role_id: 本 Agent 扮演的角色ID
        其余参数同 ReActAgent
        """
        super().__init__(
            f"{role_id}-{self.AGENT_TYPE.value}", self.SYSTEM_PROMPT, llm,
            max_steps=max_steps, temperature=temperature, keep_history=False,
        )
        self.memory_manager = memory_manager
        self.game_id = game_id
        self.role_id = role_id

    @property
    def memory(self) -> MemoryT:
        """本角色该类型 Agent 的记忆"""
        return self.memory_manager.get_agent_memory(self.game_id, self.role_id, self.AGENT_TYPE)  # type: ignore[return-value]

    def build_tools(self, memory: MemoryT) -> List[BaseTool]:
        """构建绑定到当前记忆实例的工具集"""
        raise NotImplementedError

    def build_system_prompt(self) -> str:
        return f"{self.system_prompt}\n{ROLE_RULES}\n## 你的记忆\n{self.memory.summarize(include_script=True)}"

    # ---------------- 任务执行 ----------------

    async def _run_task(self, prompt: str) -> str:
        """绑定工具后以独立的上下文执行一次任务，返回模型的最终回答"""
        self.tools = {}
        for tool in self.build_tools(self.memory):
            self.register_tool(tool)
        return (await self.run(prompt)).strip()

    async def _run_json_task(self, prompt: str, parser: Callable[[Dict[str, Any]], ResultT]) -> ResultT:
        """
        执行要求输出 JSON 对象的任务，并用 parser 转为结果。
        parser 抛出 ValueError 表示内容不合法；失败时在同一上下文中要求模型修正，避免重复执行已调用的工具。
        """
        content = await self._run_task(prompt)
        for attempt in range(1, self.MAX_PARSE_RETRIES + 2):
            try:
                return parser(self._parse_json_object(content))
            except ValueError as e:
                self.logger.warning(f"[{self.name}] 输出解析失败（第{attempt}次）：{e}，模型输出：{content}")
                if attempt > self.MAX_PARSE_RETRIES:
                    raise LLMError(f"[{self.name}] 输出解析失败，已重试{self.MAX_PARSE_RETRIES}次：{e}")
                content = (await self.react(self.RETRY_PROMPT.format(error=e))).strip()
        raise LLMError(f"[{self.name}] 输出解析失败")

    @staticmethod
    def _instruction(instruction: str) -> str:
        """player_agent 对本次任务的额外要求，拼接到任务提示词中"""
        return f"本次要求：{instruction}" if instruction else ""

    def _other_roles(self, candidates: Optional[List[str]] = None) -> List[str]:
        """可作为对象的其他角色，默认为本局已注册的所有其他角色"""
        roles = candidates if candidates is not None else self.memory_manager.roles(self.game_id)
        return [r for r in dict.fromkeys(roles) if r != self.role_id]

    @staticmethod
    def _parse_json_object(content: str) -> Dict[str, Any]:
        """从模型输出中提取第一个 JSON 对象，兼容被代码块包裹或带有多余文字的情况"""
        decoder = json.JSONDecoder()
        for i, ch in enumerate(content):
            if ch != "{":
                continue
            try:
                data, _ = decoder.raw_decode(content, i)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict):
                return data
        raise ValueError("没有找到JSON对象")
