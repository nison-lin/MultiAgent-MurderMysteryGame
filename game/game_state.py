"""一局游戏的运行状态，以及主持方通用的等待与计票工具"""

import asyncio
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Callable

from agent.player_agent import PlayerAgent
from db.entity.room_entity import PhaseEnum
from error.errors import GameError
from game.game_data import ScriptBundle
from model.character import Character
from util.log_util import LogUtil
from websocket.ws_channel import GameChannel
from websocket.ws_message import MessageType, WSMessage

_log = LogUtil()


@dataclass
class Game:
    """
    一局进行中的游戏，游戏ID即房间ID。
    phase 为主持方所处的环节，人类玩家的动作据此校验；None 表示处于环节之间，不接受任何动作。
    """
    game_id: str
    room_id: int
    script_id: int
    session_id: str
    bundle: ScriptBundle
    human: Character
    channel: GameChannel
    observer: asyncio.Queue[WSMessage]
    agents: dict[str, PlayerAgent] = field(default_factory=dict)
    chapter: int = 0
    phase: PhaseEnum | None = None
    # 当前轮到发言的角色及该次 TALK_TURN 的请求ID
    speaker: str | None = None
    turn_request_id: str | None = None
    # 指认环节的请求ID，以及人类玩家是否还能指认
    identify_request_id: str | None = None
    human_can_vote: bool = False
    # 置位表示运行中，清除表示暂停
    resume: asyncio.Event = field(default_factory=asyncio.Event)
    # 人类玩家开始离线的时间（事件循环时间）
    offline_since: float | None = None
    task: asyncio.Task | None = None
    finished: bool = False

    def __post_init__(self) -> None:
        self.resume.set()
        # 角色ID（数据库 id） -> 角色名；发言顺序按角色ID排列
        self.roles: dict[int, str] = {c.id: c.name for c in self.bundle.characters}  # type: ignore[misc]
        self.order: list[str] = [self.roles[i] for i in sorted(self.roles)]

    @property
    def human_role(self) -> str:
        """人类玩家的角色名"""
        return self.human.name  # type: ignore[return-value]

    @property
    def characters(self) -> list[Character]:
        return self.bundle.characters

    def role_of(self, character_id: int | None) -> str:
        """把客户端传来的角色ID换算为角色名"""
        if character_id is None:
            raise GameError("消息缺少对象角色 character_id")
        role = self.roles.get(character_id)
        if role is None:
            raise GameError(f"角色 {character_id} 不在本局游戏中")
        return role


async def wait_for_message(
    queue: asyncio.Queue[WSMessage],
    predicate: Callable[[WSMessage], bool],
    timeout: float,
    game_id: str = "",
) -> WSMessage | None:
    """
    从观察队列中等待第一条满足条件的消息，超时返回 None。
    等待期间取出的其他消息会被丢弃，其中的 ERROR（如某个 AI 处理阶段消息失败）记录日志。
    """
    deadline = asyncio.get_running_loop().time() + timeout
    try:
        async with asyncio.timeout_at(deadline):
            while True:
                message = await queue.get()
                if predicate(message):
                    return message
                if MessageType(message.type) == MessageType.ERROR:
                    _log.warning(
                        f"游戏 {game_id} 收到{message.data.get('from', '未知角色')}的错误报告：{message.data.get('reason')}"
                    )
    except TimeoutError:
        return None


def tally_votes(votes: dict[str, str], murderers: list[str]) -> dict[str, Any]:
    """
    统计得票：得票最多者为被指认者，平票时并列；被指认者全部是真凶时视为指认正确。
    :param votes: 投票人 -> 被指认者
    :param murderers: 真凶
    """
    tally = Counter(votes.values())
    top = max(tally.values(), default=0)
    accused = sorted(name for name, count in tally.items() if count == top) if top else []
    return {
        "votes": dict(votes),
        "tally": dict(tally.most_common()),
        "accused": accused,
        "murderers": list(murderers),
        "correct": bool(accused) and set(accused) <= set(murderers),
    }
