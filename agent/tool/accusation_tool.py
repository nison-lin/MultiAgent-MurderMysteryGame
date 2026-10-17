"""指认凶手 Agent 的工具"""

from typing import Annotated, List

from agent.memory.accusation_memory import AccusationMemory
from agent.tool.base_tool import BaseTool, create_tool
from agent.tool.memory_tool import build_memory_tools, require_text

# 单次调整嫌疑度的最大幅度
MAX_SUSPICION_DELTA = 100


def build_accusation_tools(memory: AccusationMemory) -> List[BaseTool]:
    """构建指认凶手 Agent 的工具集，推理结果只写入本 Agent 的记忆，不会公开"""

    def update_suspicion(
        name: Annotated[str, "角色名"],
        delta: Annotated[int, "嫌疑度变化量，正数为增加，负数为减少"],
        reason: Annotated[str, "调整的理由"],
    ) -> str:
        name, reason = require_text(name, "name"), require_text(reason, "reason")
        delta = max(-MAX_SUSPICION_DELTA, min(MAX_SUSPICION_DELTA, int(delta)))
        suspect = memory.update_suspicion(name, delta, reason)
        return f"{name}的嫌疑度现为{suspect.suspicion}"

    def set_motive(
        name: Annotated[str, "角色名"],
        motive: Annotated[str, "作案动机"],
    ) -> str:
        name, motive = require_text(name, "name"), require_text(motive, "motive")
        memory.add_suspect(name, motive=motive)
        return f"已记录{name}的作案动机"

    def add_clue(
        content: Annotated[str, "线索内容"],
        source: Annotated[str, "线索来源，如证据名或某人的发言"],
        suspects: Annotated[List[str] | None, "线索指向的嫌疑人"] = None,
        reasoning: Annotated[str, "由该线索得出的推论"] = "",
    ) -> str:
        content, source = require_text(content, "content"), require_text(source, "source")
        memory.add_clue(content, source, [s for s in suspects or [] if s], reasoning)
        return "已记录线索"

    def get_clues(suspect: Annotated[str, "嫌疑人角色名"]) -> str:
        suspect = require_text(suspect, "suspect")
        clues = memory.clues_of(suspect)
        if not clues:
            return f"还没有指向{suspect}的线索"
        return "\n".join(
            f"[第{c.round}轮] {c.source}：{c.content}" + (f"；推论：{c.reasoning}" if c.reasoning else "")
            for c in clues
        )

    def set_vote_intent(target: Annotated[str, "倾向投票的角色名"]) -> str:
        memory.set_vote_intent(require_text(target, "target"))
        return f"当前投票倾向：{target}"

    return build_memory_tools(memory) + [
        create_tool("update_suspicion", "调整某个角色的嫌疑度（0-100）并记录理由，角色不在嫌疑人列表中时自动添加", update_suspicion),
        create_tool("set_motive", "记录推测的某个角色的作案动机", set_motive),
        create_tool("add_clue", "把一条线索加入证据链，并标注它指向的嫌疑人与由此得出的推论", add_clue),
        create_tool("get_clues", "查看指向某个嫌疑人的全部线索", get_clues),
        create_tool("set_vote_intent", "设置当前的投票倾向，仅自己可见，正式投票前可以随时修改", set_vote_intent),
    ]
