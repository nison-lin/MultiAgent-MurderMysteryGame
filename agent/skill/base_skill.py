"""技能定义"""

from enum import Enum
from typing import List

from pydantic import BaseModel, Field

from agent.memory.memory_enum import AgentTypeEnum


class SkillRoleEnum(str, Enum):
    """技能适用的角色身份"""
    MURDERER = "murderer"  # 凶手
    INNOCENT = "innocent"  # 非凶手

    @classmethod
    def of(cls, is_murderer: bool) -> "SkillRoleEnum":
        return cls.MURDERER if is_murderer else cls.INNOCENT


class Skill(BaseModel):
    """
    一个技能，对应 skills/<name>/SKILL.md。
    always 为 True 时正文直接注入系统提示词；否则只在提示词中列出名称和描述，由模型通过 load_skill 按需读取。
    roles / agents 为空表示适用于所有身份 / 所有子 Agent。
    """

    name: str
    description: str
    always: bool = False
    roles: List[SkillRoleEnum] = Field(default_factory=list)
    agents: List[AgentTypeEnum] = Field(default_factory=list)
    content: str

    def matches(self, agent_type: AgentTypeEnum, is_murderer: bool) -> bool:
        """是否适用于该类型的子 Agent 与角色身份"""
        if self.agents and agent_type not in self.agents:
            return False
        return not self.roles or SkillRoleEnum.of(is_murderer) in self.roles
