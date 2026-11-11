"""按需读取技能的工具"""

from typing import Annotated, List

from agent.skill.base_skill import Skill
from agent.skill.skill_registry import LOAD_SKILL_TOOL
from agent.tool.base_tool import BaseTool, create_tool
from agent.tool.memory_tool import require_text


def build_skill_tools(skills: List[Skill]) -> List[BaseTool]:
    """
    构建 load_skill 工具，只能读取传入的按需技能（always 为 False），
    其他身份或其他子 Agent 的技能不会出现在这里。没有按需技能时返回空列表。
    """
    available = {skill.name: skill for skill in skills if not skill.always}
    if not available:
        return []

    def load_skill(name: Annotated[str, "技能名称，必须是系统提示词“可用技能”中列出的名称"]) -> str:
        name = require_text(name, "name")
        skill = available.get(name)
        if skill is None:
            raise ValueError(f"技能 {name} 不存在，可用技能：{'、'.join(available)}")
        return skill.content

    return [
        create_tool(LOAD_SKILL_TOOL, "读取一个可用技能的全文，在需要该技能的指导时调用", load_skill),
    ]
