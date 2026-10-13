"""讨论 Agent"""

from typing import List

from agent.memory.discussion_memory import DiscussionMemory
from agent.memory.memory_enum import AgentTypeEnum
from agent.sub_agent import SubAgent
from agent.tool.base_tool import BaseTool
from agent.tool.discussion_tool import build_discussion_tools

SYSTEM_PROMPT = """
你是剧本杀游戏中一名玩家的公开讨论模块，负责在轮到该玩家时以其角色身份发言。
你只处理调度方交给你的发言任务，不负责私聊，也不做最终的凶手指认。

## 发言原则
1. 发言要回应讨论的进展：回答对你的质疑、追问别人的漏洞、推进当前讨论焦点，不要重复自己说过的话。
2. 发言前梳理其他人的观点，有新的理解时用 note_opinion 记下；讨论焦点发生变化时用 set_focus 更新。
3. 需要查阅更早的发言或其他记忆时，用 get_speeches / search_memory。
4. 公开发言所有人都能听到，不要暴露对你不利的私有信息。
"""

SPEAK_PROMPT = """
现在轮到你在第{round}轮公开发言。
{instruction}
先结合本轮及之前的发言整理思路（可以使用工具），然后只输出你的发言内容本身，不要加引号或说明，200字以内。
"""


class DiscussionAgent(SubAgent[DiscussionMemory]):
    """
    讨论 Agent：在公开讨论中与其他角色交替发言。
    发言顺序由 player_agent / 游戏流程控制，本 Agent 只在被调用时生成一次发言，并公开到公共记忆。
    """

    AGENT_TYPE = AgentTypeEnum.DISCUSSION
    SYSTEM_PROMPT = SYSTEM_PROMPT

    def build_tools(self, memory: DiscussionMemory) -> List[BaseTool]:
        return build_discussion_tools(memory)

    async def speak(self, instruction: str = "") -> str:
        """
        生成本角色的一次公开发言，并记录为公共记忆。
        :param instruction: player_agent 对本次发言的额外要求，如“回应王五对你的质疑”
        :return: 发言内容
        """
        memory = self.memory
        prompt = SPEAK_PROMPT.format(round=memory.current_round, instruction=self._instruction(instruction))
        content = await self._run_task(prompt)
        memory.add_speech(content)
        return content
