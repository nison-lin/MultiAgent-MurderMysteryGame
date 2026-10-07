"""ReAct Agent"""

import json
from typing import Any, Dict, List, Optional

from client.llm_client import LLMClientWrapper
from agent.tool.base_tool import BaseTool
from error.errors import LLMError
from util.log_util import LogUtil

class ReActAgent:
    """
    ReAct Agent，边调用工具边思考。

    循环流程：
        Thought   模型基于上下文进行推理
        Action    模型决定调用某个工具（function calling）
        Observation 工具执行结果回填到上下文
    重复上述过程，直到模型不再调用工具而直接给出最终回答，或达到最大步数。

    子类通常只需要：
        1. 提供 system_prompt
        2. 通过 tools 参数或 register_tool() 注册工具
        3. 按需重写 build_system_prompt() / on_final_answer() 等钩子
    """

    FORCE_ANSWER_PROMPT = "已达到最大推理步数，请不要再调用工具，直接根据已有信息给出最终回答。"

    def __init__(
        self,
        name: str,
        system_prompt: str,
        llm: Optional[LLMClientWrapper] = None,
        tools: Optional[List[BaseTool]] = None,
        max_steps: int = 5,
        temperature: float = 0.7,
        keep_history: bool = True,
    ):
        """
        :param name: Agent名称，用于日志区分
        :param system_prompt: 系统提示词，定义Agent的角色与行为
        :param llm: LLM客户端，未提供时使用默认配置创建
        :param tools: 初始工具列表
        :param max_steps: 单次 run 中最多的 推理-行动 轮数
        :param temperature: 模型温度
        :param keep_history: 是否在多次 run 之间保留对话历史
        """
        self.name = name
        self.system_prompt = system_prompt
        self.llm = llm or LLMClientWrapper()
        self.max_steps = max_steps
        self.temperature = temperature
        self.keep_history = keep_history
        self.logger = LogUtil()

        self.tools: Dict[str, BaseTool] = {}
        for tool in tools or []:
            self.register_tool(tool)

        self.history: List[Dict[str, Any]] = []

    # ---------------- 工具管理 ----------------

    def register_tool(self, tool: BaseTool) -> None:
        """注册工具，同名工具会被覆盖"""
        self.tools[tool.name] = tool

    def remove_tool(self, name: str) -> None:
        """移除工具"""
        self.tools.pop(name, None)

    # ---------------- 可重写的钩子 ----------------

    def build_system_prompt(self) -> str:
        """构建系统提示词，子类可重写以注入动态上下文（如游戏状态）"""
        return self.system_prompt

    async def on_final_answer(self, answer: str) -> str:
        """得到最终回答后的处理，子类可重写做后处理或校验"""
        return answer

    # ---------------- 核心流程 ----------------

    def reset(self) -> None:
        """清空对话历史"""
        self.history.clear()

    async def run(self, user_input: str) -> str:
        """
        执行一次完整的 ReAct 循环，返回经过 on_final_answer 处理后的最终回答。
        """
        if not self.keep_history:
            self.reset()
        answer = await self.react(user_input)
        return await self.on_final_answer(answer)

    async def react(self, user_input: str) -> str:
        """
        ReAct 循环本体：基于当前历史继续对话，返回模型的原始回答，不触发 on_final_answer。
        供 run() 及子类（如 PlanAgent 逐步执行时）复用。
        """
        self.history.append({"role": "user", "content": user_input})

        # 没有工具时退化为普通对话
        if not self.tools:
            answer = await self.llm.think_without_tools(self._build_messages(), self.temperature)  # type: ignore
            return self._finish(answer)

        tool_schemas = [tool.to_schema() for tool in self.tools.values()]

        for step in range(1, self.max_steps + 1):
            message = await self.llm.think_with_tools(self._build_messages(), self.temperature, tool_schemas)  # type: ignore

            # 无工具调用，说明模型已给出最终回答
            if not message.tool_calls:
                return self._finish(message.content or "")

            # Thought：模型在调用工具前输出的推理内容
            if message.content:
                self.logger.log(f"[{self.name}] Step {step} Thought: {message.content}")

            self.history.append({
                "role": "assistant",
                "content": message.content,
                "tool_calls": [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {"name": call.function.name, "arguments": call.function.arguments},
                    }
                    for call in message.tool_calls
                ],
            })

            # Action -> Observation
            for call in message.tool_calls:
                self.logger.log(f"[{self.name}] Step {step} Action: {call.function.name}({call.function.arguments})")
                observation = await self._execute_tool(call.function.name, call.function.arguments)
                self.logger.log(f"[{self.name}] Step {step} Observation: {observation}")
                self.history.append({
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": observation,
                })

        # 超过最大步数，强制模型给出最终回答
        self.logger.warning(f"[{self.name}] 达到最大步数 {self.max_steps}，强制生成最终回答")
        messages = self._build_messages() + [{"role": "user", "content": self.FORCE_ANSWER_PROMPT}]
        answer = await self.llm.think_without_tools(messages, self.temperature)  # type: ignore
        return self._finish(answer)

    # ---------------- 内部方法 ----------------

    def _build_messages(self) -> List[Dict[str, Any]]:
        """拼接系统提示词与历史消息"""
        return [{"role": "system", "content": self.build_system_prompt()}] + self.history

    def _finish(self, answer: str) -> str:
        """校验并记录模型回答"""
        if not answer:
            raise LLMError(f"[{self.name}] 模型未给出最终回答")
        self.history.append({"role": "assistant", "content": answer})
        return answer

    async def _execute_tool(self, name: str, arguments: str) -> str:
        """
        执行工具并将结果转为字符串。
        工具异常不会中断循环，而是作为 Observation 反馈给模型，让其自行修正。
        """
        tool = self.tools.get(name)
        if tool is None:
            return f"错误：工具 {name} 不存在，可用工具：{', '.join(self.tools)}"

        try:
            kwargs = json.loads(arguments) if arguments else {}
        except json.JSONDecodeError as e:
            return f"错误：工具参数不是合法的JSON：{e}"

        try:
            result = await tool.invoke(**kwargs)
        except Exception as e:
            self.logger.warning(f"[{self.name}] 工具 {name} 执行失败：{e}")
            return f"错误：工具 {name} 执行失败：{e}"

        if isinstance(result, str):
            return result
        try:
            return json.dumps(result, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            return str(result)
