"""指认凶手 Agent"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from agent.memory.accusation_memory import AccusationMemory
from agent.memory.memory_enum import AgentTypeEnum
from agent.sub_agent import SubAgent
from agent.tool.accusation_tool import build_accusation_tools
from agent.tool.base_tool import BaseTool
from error.errors import DataError

SYSTEM_PROMPT = """
你是剧本杀游戏中一名玩家的推理模块，负责以该玩家的角色身份综合已知信息，推理出凶手。
你只处理调度方交给你的推理与指认任务，不负责发言和私聊。

## 推理方法
1. 从证据、剧本、发言和私聊中提取与案件有关的线索，用 add_clue 加入证据链，标注指向的嫌疑人和推论。
2. 分析每个嫌疑人的动机、作案时间与手段，用 set_motive 记录动机，用 update_suspicion 调整嫌疑度并写明理由。
3. 注意证词之间的矛盾、时间线的空白和反常的举动；新信息推翻旧判断时要及时修正，不要固执己见。
4. 用 set_vote_intent 记录当前最可能的凶手。
5. 证据链与嫌疑人档案已在记忆摘要中，需要更多细节时用 search_memory / get_clues 查阅。
6. 如果你就是凶手，你的推理目标是找出最有说服力的替罪羊，而不是真相。
"""

ANALYZE_PROMPT = """
请根据目前掌握的所有信息更新你的推理：
- 把新的线索加入证据链（已记录的线索不要重复记录）
- 调整各嫌疑人的嫌疑度与动机
- 更新投票倾向
{instruction}
完成后用200字以内总结：目前最可疑的是谁、主要依据、还有哪些疑点需要求证。
"""

ACCUSE_PROMPT = """
现在进入指认凶手环节，你必须从以下角色中指认一人为凶手：{candidates}
{instruction}
如有需要，先补充更新证据链与嫌疑度，然后给出最终指认。

## 输出格式
只输出一个JSON对象，不要输出其他内容：
{{"murderer": "角色名", "reason": "指认理由，结合关键证据说明动机、时间与手段，200字以内"}}
"""


@dataclass
class Accusation:
    """指认结果"""
    murderer: str
    reason: str


class AccusationAgent(SubAgent[AccusationMemory]):
    """
    指认凶手 Agent：综合已知信息推理凶手。
    analyze 只更新私有的推理记录（嫌疑人、证据链、投票倾向），可以在游戏过程中多次调用；
    accuse 给出最终指认并作为公开投票记录。
    """

    AGENT_TYPE = AgentTypeEnum.ACCUSATION
    SYSTEM_PROMPT = SYSTEM_PROMPT

    def build_tools(self, memory: AccusationMemory) -> List[BaseTool]:
        return build_accusation_tools(memory)

    async def analyze(self, instruction: str = "") -> str:
        """
        更新推理，结果只写入本 Agent 的记忆。
        :param instruction: player_agent 对本次推理的额外要求，如“重点分析新公开的证据”
        :return: 推理总结，可供 player_agent 安排发言或私聊时参考
        """
        return await self._run_task(ANALYZE_PROMPT.format(instruction=self._instruction(instruction)))

    async def accuse(self, candidates: Optional[List[str]] = None, instruction: str = "") -> Accusation:
        """
        指认凶手，并把投票公开到公共记忆。
        :param candidates: 可以指认的角色，默认为本局的所有其他角色
        """
        candidates = self._other_roles(candidates)
        if not candidates:
            raise DataError(f"[{self.name}] 没有可以指认的角色")
        prompt = ACCUSE_PROMPT.format(candidates="、".join(candidates), instruction=self._instruction(instruction))
        accusation = await self._run_json_task(prompt, lambda data: self._parse_accusation(data, candidates))
        self.memory.cast_vote(accusation.murderer, accusation.reason)
        return accusation

    @staticmethod
    def _parse_accusation(data: Dict[str, Any], candidates: List[str]) -> Accusation:
        murderer = data.get("murderer")
        if murderer not in candidates:
            raise ValueError(f"murderer 必须是以下角色之一：{'、'.join(candidates)}")
        return Accusation(murderer, str(data.get("reason") or "").strip())
