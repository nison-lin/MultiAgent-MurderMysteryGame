"""Plan-and-Execute Agent"""

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Union

from client.llm_client import LLMClientWrapper
from agent.react_agent import ReActAgent
from agent.tool.base_tool import BaseTool


@dataclass
class StepResult:
    """单个计划步骤的执行结果"""
    step: str
    result: str


class PlanAgent(ReActAgent):
    """
    先规划后执行的Agent，适合需要多步完成的复杂任务（如生成剧本）。

    流程：
        plan       让模型把任务拆解为有序步骤
        execute    逐步执行，每一步都是一次独立的 ReAct 循环，并带上之前步骤的结果
        summarize  汇总所有步骤结果，得到最终回答
    run() 会依次调用以上三个方法；也可以单独调用，例如先 plan 再人工调整步骤后 execute。
    """

    PLAN_PROMPT = (
        "请将下面的任务拆解为按顺序执行的步骤，每个步骤应当具体、可独立完成，并结合可用工具考虑如何实现。\n"
        "如有需要，可以先调用工具收集信息，再制定计划。\n\n"
        "任务：{task}\n\n"
        "最终只输出一个JSON字符串数组，不要输出其他内容，例如：[\"步骤1\", \"步骤2\"]"
    )

    STEP_PROMPT = (
        "总任务：{task}\n\n"
        "已完成的步骤及结果：\n{history}\n\n"
        "当前步骤：{step}\n"
        "请只完成当前步骤，并给出该步骤的结果。"
    )

    SUMMARY_PROMPT = (
        "总任务：{task}\n\n"
        "各步骤执行结果：\n{history}\n\n"
        "请根据以上结果，给出总任务的最终回答。"
    )

    def __init__(
        self,
        name: str,
        system_prompt: str,
        llm: Optional[LLMClientWrapper] = None,
        tools: Optional[List[BaseTool]] = None,
        max_steps: int = 5,
        temperature: float = 0.7,
        max_plan_steps: int = 8,
    ):
        """
        :param max_steps: 每个计划步骤内 ReAct 循环的最大轮数
        :param max_plan_steps: 计划最多包含的步骤数
        其余参数同 ReActAgent
        """
        super().__init__(name, system_prompt, llm, tools, max_steps, temperature, keep_history=False)
        self.max_plan_steps = max_plan_steps

    async def run(self, task: str) -> str:
        """规划 -> 执行 -> 汇总，返回经过 on_final_answer 处理后的最终回答"""
        steps = await self.plan(task)
        results = await self.execute(task, steps)
        answer = await self.summarize(task, results)
        return await self.on_final_answer(answer)

    async def plan(self, task: str, prompt: Optional[str] = None) -> List[str]:
        """
        让模型将任务拆解为步骤列表；解析失败时把整个任务作为单一步骤。
        通过 react() 规划：工具以 function calling 方式提供给模型，模型可先调用工具收集信息再给出计划。
        :param prompt: 已格式化好的规划提示词，为空时使用 PLAN_PROMPT 并以 task 格式化
        """
        self.reset()
        if prompt is None:
            prompt = self.PLAN_PROMPT.format(task=task)
        content = await self.react(prompt)

        parsed = self._parse_steps(content)
        if isinstance(parsed, dict):
            parsed = [parsed]
        # 字典步骤转为JSON文本，便于后续拼接到提示词中
        steps = [s if isinstance(s, str) else json.dumps(s, ensure_ascii=False) for s in parsed]
        if not steps:
            self.logger.warning(f"[{self.name}] 计划解析失败，按单步执行。模型输出：{content}")
            steps = [task]
        if len(steps) > self.max_plan_steps:
            self.logger.warning(f"[{self.name}] 计划步骤数 {len(steps)} 超过上限，截断为 {self.max_plan_steps}")
            steps = steps[:self.max_plan_steps]

        self.logger.log(f"[{self.name}] Plan: {steps}")
        return steps

    async def execute(self, task: str, steps: List[str]) -> List[StepResult]:
        """
        逐步执行计划。每一步清空历史后独立运行 ReAct 循环，
        之前步骤的结果通过提示词传入，避免上下文被工具调用细节撑大。
        """
        results: List[StepResult] = []
        for i, step in enumerate(steps, 1):
            self.reset()
            prompt = self.STEP_PROMPT.format(task=task, history=self._format_results(results), step=step)
            result = await self.react(prompt)
            self.logger.log(f"[{self.name}] Plan step {i}/{len(steps)} done: {step}")
            results.append(StepResult(step, result))
        return results

    async def summarize(self, task: str, results: List[StepResult]) -> str:
        """汇总各步骤结果，生成最终回答"""
        messages = [
            {"role": "system", "content": self.build_system_prompt()},
            {"role": "user", "content": self.SUMMARY_PROMPT.format(task=task, history=self._format_results(results))},
        ]
        answer = await self.llm.think_without_tools(messages, self.temperature)  # type: ignore
        return self._finish(answer)

    @staticmethod
    def _format_results(results: List[StepResult]) -> str:
        """将步骤结果格式化为提示词文本"""
        if not results:
            return "无"
        return "\n\n".join(f"{i}. {r.step}\n结果：{r.result}" for i, r in enumerate(results, 1))

    @staticmethod
    def _parse_steps(content: str) -> Union[Dict[str, Any], List[Any]]:
        """
        从模型输出中提取JSON，兼容被 ```json 代码块包裹或带有多余文字的情况。
        JSON对象解析为字典；JSON数组解析为列表（元素为对象时即为字典列表）；解析失败返回空列表。
        """
        decoder = json.JSONDecoder()
        # 依次尝试从每个 '{' 或 '[' 处解析，跳过前面文字中可能出现的括号
        for i, ch in enumerate(content):
            if ch not in "{[":
                continue
            try:
                data, _ = decoder.raw_decode(content, i)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict):
                return data
            if isinstance(data, list):
                # 去掉空字符串元素，字典等其他元素原样保留
                return [s.strip() if isinstance(s, str) else s for s in data
                        if not isinstance(s, str) or s.strip()]
        return []
