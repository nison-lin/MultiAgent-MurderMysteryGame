"""游戏消息通道：在同一局游戏的人类玩家、AI 玩家与主持方之间路由消息"""

import asyncio
from typing import Optional

from websocket.ws_manager import get_ws_manager
from websocket.ws_message import WSMessage
from error.errors import WebSocketError
from util.log_util import LogUtil

_log = LogUtil()


class GameChannel:
    """
    一局游戏的消息通道，所有玩家间的互动统一使用 WSMessage，按角色ID投递：
        人类玩家   经 ConnectionManager 推送到其 WebSocket 会话
        AI 玩家    投递到进程内的收件队列
        观察者     主持方等订阅者会收到经过通道的每一条消息，用于掌握发言是否完成、指认结果等

    消息约定：data["from"] 为发送方角色ID，data["to"] 为接收方角色ID（仅私聊），data["content"] 为内容。
    人类玩家发来的 TALK / PRIVATE_TALK / IDENTIFY 由游戏流程写入记忆后，再经 send / broadcast 转发给其他玩家。
    """

    def __init__(self, game_id: str):
        self.game_id = game_id
        # 角色ID -> 人类玩家的会话ID
        self._humans: dict[str, str] = {}
        # 角色ID -> AI 玩家的收件队列
        self._agents: dict[str, asyncio.Queue[WSMessage]] = {}
        self._observers: list[asyncio.Queue[WSMessage]] = []

    # ---------------- 成员 ----------------

    def join_human(self, role_id: str, session_id: str) -> None:
        """人类玩家加入通道，重连时以新会话覆盖"""
        self._check_role(role_id, self._humans)
        self._humans[role_id] = session_id

    def join_agent(self, role_id: str) -> asyncio.Queue[WSMessage]:
        """AI 玩家加入通道，返回其收件队列"""
        self._check_role(role_id, self._agents)
        return self._agents.setdefault(role_id, asyncio.Queue())

    def leave(self, role_id: str) -> None:
        """玩家离开通道"""
        self._humans.pop(role_id, None)
        self._agents.pop(role_id, None)

    def roles(self) -> list[str]:
        """通道中的所有玩家角色"""
        return list(self._humans) + list(self._agents)

    def observe(self) -> asyncio.Queue[WSMessage]:
        """订阅通道中的全部消息"""
        queue: asyncio.Queue[WSMessage] = asyncio.Queue()
        self._observers.append(queue)
        return queue

    def unobserve(self, queue: asyncio.Queue[WSMessage]) -> None:
        """取消订阅"""
        if queue in self._observers:
            self._observers.remove(queue)

    # ---------------- 投递 ----------------

    async def send(self, role_id: str, message: WSMessage) -> bool:
        """把消息投递给某个玩家，并抄送观察者；人类玩家不在线时返回 False"""
        if role_id not in self._humans and role_id not in self._agents:
            raise WebSocketError(f"游戏 {self.game_id} 中角色 {role_id} 不在通道内")
        self.notify(message)
        return await self._deliver(role_id, message)

    async def broadcast(self, message: WSMessage, exclude: Optional[str] = None) -> None:
        """把消息投递给除 exclude 外的所有玩家，并抄送观察者"""
        self.notify(message)
        for role_id in self.roles():
            if role_id != exclude:
                await self._deliver(role_id, message)

    def notify(self, message: WSMessage) -> None:
        """只投递给观察者，如玩家处理失败时的错误报告"""
        for queue in self._observers:
            queue.put_nowait(message.model_copy(deep=True))

    async def _deliver(self, role_id: str, message: WSMessage) -> bool:
        queue = self._agents.get(role_id)
        if queue is not None:
            # 每个收件人拿到独立副本，避免一方修改影响其他人
            queue.put_nowait(message.model_copy(deep=True))
            return True
        session_id = self._humans[role_id]
        delivered = await get_ws_manager().send(session_id, message)
        if not delivered:
            _log.warning(f"WS 游戏 {self.game_id} 的玩家 {role_id} 不在线，消息未送达：type={message.type}")
        return delivered

    def _check_role(self, role_id: str, own: dict) -> None:
        """同一角色不能同时作为人类玩家和 AI 玩家"""
        other = self._agents if own is self._humans else self._humans
        if role_id in other:
            raise WebSocketError(f"游戏 {self.game_id} 中角色 {role_id} 已被另一类玩家占用")


_channels: dict[str, GameChannel] = {}


def create_channel(game_id: str) -> GameChannel:
    """创建一局游戏的消息通道"""
    if game_id in _channels:
        raise WebSocketError(f"游戏 {game_id} 的消息通道已存在")
    _channels[game_id] = GameChannel(game_id)
    return _channels[game_id]


def get_channel(game_id: str) -> GameChannel:
    """获取一局游戏的消息通道"""
    channel = _channels.get(game_id)
    if channel is None:
        raise WebSocketError(f"游戏 {game_id} 的消息通道不存在，请先调用 create_channel")
    return channel


def remove_channel(game_id: str) -> None:
    """游戏结束后释放消息通道"""
    _channels.pop(game_id, None)
