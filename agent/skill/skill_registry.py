"""技能注册表：从 skills 目录加载技能，按子 Agent 类型与角色身份筛选"""

import functools
from pathlib import Path
from typing import Dict, List

import yaml
from pydantic import ValidationError

from agent.memory.memory_enum import AgentTypeEnum
from agent.skill.base_skill import Skill
from error.errors import DataError

# 默认技能目录：项目根目录下的 skills/
DEFAULT_SKILL_DIR = Path(__file__).resolve().parent.parent.parent / "skills"
SKILL_FILE = "SKILL.md"
LOAD_SKILL_TOOL = "load_skill"


class SkillRegistry:
    """
    技能注册表。技能文件格式：
        ---
        name: 技能名（必须与所在目录名一致）
        description: 一句话描述
        always: true / false
        roles: [murderer, innocent]           # 可省略
        agents: [discussion, private_chat]    # 可省略
        ---
        正文（Markdown）
    格式错误时在加载阶段抛出 DataError，避免游戏进行到一半才发现。
    """

    def __init__(self, skills: List[Skill]):
        self.skills: Dict[str, Skill] = {}
        for skill in skills:
            if skill.name in self.skills:
                raise DataError(f"技能名称重复：{skill.name}")
            self.skills[skill.name] = skill

    @classmethod
    def load(cls, directory: Path | str = DEFAULT_SKILL_DIR) -> "SkillRegistry":
        """加载目录下所有 */SKILL.md，按目录名排序，保证注入提示词的顺序稳定"""
        directory = Path(directory)
        if not directory.is_dir():
            raise DataError(f"技能目录不存在：{directory}")
        return cls([cls._parse(path) for path in sorted(directory.glob(f"*/{SKILL_FILE}"))])

    @staticmethod
    def _parse(path: Path) -> Skill:
        """解析单个技能文件"""
        text = path.read_text(encoding="utf-8-sig")
        parts = text.split("---", 2)
        if len(parts) < 3 or parts[0].strip():
            raise DataError(f"技能文件缺少 --- 包裹的 frontmatter：{path}")
        try:
            meta = yaml.safe_load(parts[1]) or {}
        except yaml.YAMLError as e:
            raise DataError(f"技能文件 frontmatter 不是合法的YAML：{path}：{e}") from e
        if not isinstance(meta, dict):
            raise DataError(f"技能文件 frontmatter 必须是键值对：{path}")

        try:
            skill = Skill.model_validate({**meta, "content": parts[2].strip()})
        except ValidationError as e:
            raise DataError(f"技能文件格式错误：{path}：{e}") from e
        if skill.name != path.parent.name:
            raise DataError(f"技能名称 {skill.name} 与目录名 {path.parent.name} 不一致：{path}")
        if not skill.description.strip() or not skill.content:
            raise DataError(f"技能的描述与正文不能为空：{path}")
        return skill

    def select(self, agent_type: AgentTypeEnum, is_murderer: bool) -> List[Skill]:
        """适用于该类型子 Agent 与角色身份的技能"""
        return [skill for skill in self.skills.values() if skill.matches(agent_type, is_murderer)]

    @staticmethod
    def render_prompt(skills: List[Skill]) -> str:
        """生成注入系统提示词的技能文本：常驻技能的正文 + 按需技能的目录"""
        sections = [skill.content for skill in skills if skill.always]
        on_demand = [skill for skill in skills if not skill.always]
        if on_demand:
            lines = "\n".join(f"- {skill.name}：{skill.description}" for skill in on_demand)
            sections.append(f"## 可用技能\n需要时用 {LOAD_SKILL_TOOL} 按名称读取技能全文：\n{lines}")
        return "\n\n".join(sections)


@functools.lru_cache(maxsize=1)
def get_skill_registry() -> SkillRegistry:
    """默认技能目录的注册表，整个进程只加载一次"""
    return SkillRegistry.load()
