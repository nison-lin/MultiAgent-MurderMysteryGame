"""私聊 Agent"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from agent.memory.memory_enum import AgentTypeEnum
from agent.memory.private_chat_memory import PrivateChatMemory
from agent.sub_agent import SubAgent
from agent.tool.base_tool import BaseTool
from agent.tool.private_chat_tool import build_private_chat_tools
from error.errors import DataError

SYSTEM_PROMPT = """
你是剧本杀游戏中一名玩家的私聊模块，负责以该玩家的角色身份与其他角色一对一私聊。
你只处理调度方交给你的私聊任务，不参与公开讨论，也不做最终的凶手指认。

## 私聊原则
1. 私聊的目的是交换信息、试探对方、求证疑点、结盟或澄清嫌疑，每句话都要有目的。
2. 不要把与其他人的私聊内容透露给当前对象，除非这样做对你有利。
3. 得到重要信息、达成约定或对对方有了新的判断时，用 note_partner 记下来。
4. 需要回忆细节时，用 search_memory / get_conversation 查阅记忆。
"""

REPLY_PROMPT = """
{partner}刚刚私聊了你，请结合与{partner}的私聊记录回复对方最新的消息。
{instruction}
只输出要发送给{partner}的消息本身，不要加引号或说明，150字以内。
"""

INITIATE_PROMPT = """
你决定主动私聊{partner}，目的是：{purpose}
{instruction}
请写出发给{partner}的第一条消息，只输出消息本身，不要加引号或说明，150字以内。
"""

DECIDE_PROMPT = """
请判断现在是否需要主动发起一次私聊。
可以私聊的角色：{candidates}

## 判断依据
- 有需要向某人求证的疑点、需要交换的信息，或需要拉拢、澄清的关系时才发起。
- 没有明确目的就不要发起；刚聊过且没有新进展的对象不要重复私聊。
- 判断前可以用 list_partners / get_conversation 查看与各人的私聊记录。

## 输出格式
只输出一个JSON对象，不要输出其他内容：
{{"should_chat": true, "target": "角色名", "purpose": "私聊目的"}}
不需要私聊时输出：{{"should_chat": false, "target": null, "purpose": "不私聊的理由"}}
"""


@dataclass
class ChatDecision:
    """是否主动发起私聊的判断结果"""
    should_chat: bool
    target: str | None
    purpose: str


class PrivateChatAgent(SubAgent[PrivateChatMemory]):
    """
    私聊 Agent：回复其他角色的私聊，并判断要不要主动向某人发起私聊。

    私聊消息由发送方通过 MemoryManager.record_private_chat 写入双方记忆：
        本 Agent 生成的消息（reply / initiate）会自动记录；
        对方发来的消息由对方的私聊 Agent 或游戏流程（人类玩家）负责记录，调用 reply 前应已写入。
    decide 只给出判断，不会发起私聊；是否采纳由 player_agent 决定，采纳后再调用 initiate。
    """

    AGENT_TYPE = AgentTypeEnum.PRIVATE_CHAT
    SYSTEM_PROMPT = SYSTEM_PROMPT

    def build_tools(self, memory: PrivateChatMemory) -> List[BaseTool]:
        return build_private_chat_tools(memory)

    async def reply(self, partner: str, instruction: str = "") -> str:
        """
        回复某个角色最新的私聊消息，并记录到双方记忆。
        :param partner: 发来私聊的角色
        :param instruction: player_agent 对本次回复的额外要求，如“试探对方案发时的行踪”
        :return: 回复内容
        """
        memory = self.memory
        last = memory.get_conversation(partner, limit=1)
        if not last or last[0].source != partner:
            raise DataError(f"[{self.name}] 没有来自 {partner} 的待回复私聊消息")
        memory.start_chat(partner)
        content = await self._run_task(REPLY_PROMPT.format(partner=partner, instruction=self._instruction(instruction)))
        self._send(partner, content)
        return content

    async def decide(self, candidates: Optional[List[str]] = None) -> ChatDecision:
        """
        判断是否需要主动发起私聊，不会产生任何对外的行动。
        判断需要纵观与所有人的私聊记录，因此会先结束当前私聊。
        :param candidates: 可以私聊的角色，默认为本局的所有其他角色
        """
        candidates = self._other_roles(candidates)
        if not candidates:
            return ChatDecision(False, None, "没有可以私聊的角色")
        self.memory.end_chat()
        prompt = DECIDE_PROMPT.format(candidates="、".join(candidates))
        return await self._run_json_task(prompt, lambda data: self._parse_decision(data, candidates))

    async def initiate(self, partner: str, purpose: str, instruction: str = "") -> str:
        """
        向某个角色发起私聊，生成第一条消息并记录到双方记忆。
        :param purpose: 私聊目的，通常来自 decide 的结果
        :return: 消息内容
        """
        if partner == self.role_id:
            raise DataError(f"[{self.name}] 不能私聊自己")
        self.memory.start_chat(partner)
        prompt = INITIATE_PROMPT.format(partner=partner, purpose=purpose, instruction=self._instruction(instruction))
        content = await self._run_task(prompt)
        self._send(partner, content)
        return content

    def end_chat(self) -> None:
        """结束当前私聊"""
        self.memory.end_chat()

    def _send(self, partner: str, content: str) -> None:
        """记录本角色发出的私聊消息"""
        self.memory_manager.record_private_chat(self.game_id, self.role_id, partner, content)

    @staticmethod
    def _parse_decision(data: Dict[str, Any], candidates: List[str]) -> ChatDecision:
        should_chat = data.get("should_chat")
        if not isinstance(should_chat, bool):
            raise ValueError("should_chat 必须是布尔值")
        purpose = str(data.get("purpose") or "")
        if not should_chat:
            return ChatDecision(False, None, purpose)
        target = data.get("target")
        if target not in candidates:
            raise ValueError(f"target 必须是以下角色之一：{'、'.join(candidates)}")
        return ChatDecision(True, target, purpose)
