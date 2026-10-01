"""WebSocket连接管理：按会话维护连接，负责推送与心跳巡检"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from fastapi import WebSocket

from core.websocket.ws_config import WebSocketConfig, get_ws_config
from core.websocket.ws_message import WSMessage
from error.errors import WebSocketError
from util.log_util import LogUtil
from util.uuid_util import create_uuid

_log = LogUtil()


@dataclass
class Connection:
    """一条已建立的连接。单人游戏，一个会话对应一条连接"""

    websocket: WebSocket
    session_id: str
    connected_at: datetime = field(default_factory=datetime.now)
    # 最后一次收到该客户端消息的时间，用于心跳判活
    last_seen: datetime = field(default_factory=datetime.now)

    def touch(self) -> None:
        """刷新活跃时间"""
        self.last_seen = datetime.now()

    def is_stale(self, timeout: int) -> bool:
        """判断连接是否已超过timeout秒未活跃"""
        return (datetime.now() - self.last_seen).total_seconds() > timeout


class ConnectionManager:
    """连接管理器。以会话ID为键持有连接，结构改动都在锁内完成"""

    def __init__(self, config: Optional[WebSocketConfig] = None):
        self.config = config or get_ws_config()
        # session_id -> Connection
        self._connections: dict[str, Connection] = {}
        self._lock = asyncio.Lock()
        self._monitor: Optional[asyncio.Task] = None

    async def connect(self, websocket: WebSocket, session_id: str | None = None) -> Connection:
        """接受连接并登记。同一会话重连时挤掉旧连接（刷新页面即走这条路）"""
        await websocket.accept()
        session_id = session_id or create_uuid("session_id")

        async with self._lock:
            replaced = self._connections.get(session_id)
            if replaced is None and len(self._connections) >= self.config.maxConnections:
                raise WebSocketError(f"并发会话数已达上限{self.config.maxConnections}")
            connection = Connection(websocket=websocket, session_id=session_id)
            self._connections[session_id] = connection

        if replaced is not None:
            # 旧连接在锁外关闭，关闭失败不影响新连接
            await self._close(replaced, reason="该会话已在别处重新连接")
            _log.log(f"WS 会话重连，旧连接已断开：session={session_id}")

        _log.log(f"WS 连接建立：session={session_id}")
        return connection

    async def disconnect(self, connection: Connection) -> None:
        """注销连接。仅当登记的仍是同一对象时才移除，避免误删重连后的新连接"""
        async with self._lock:
            if self._connections.get(connection.session_id) is connection:
                del self._connections[connection.session_id]
        _log.log(f"WS 连接关闭：session={connection.session_id}")

    async def _close(self, connection: Connection, reason: str = "") -> None:
        """关闭一条连接，忽略已断开导致的异常"""
        try:
            # 1000 = 正常关闭；reason 超长会被部分客户端拒绝，这里截断
            await connection.websocket.close(code=1000, reason=reason[:120])
        except Exception:
            pass

    async def send(self, session_id: str, message: WSMessage) -> bool:
        """向会话推送一条消息。会话不在线返回False，发送失败则断开该连接"""
        async with self._lock:
            connection = self._connections.get(session_id)
        if connection is None:
            return False

        try:
            await asyncio.wait_for(
                connection.websocket.send_text(message.to_json()),
                timeout=self.config.sendTimeout,
            )
            return True
        except Exception as e:
            _log.warning(f"WS 发送失败，断开连接：session={session_id} 原因={e}")
            await self.disconnect(connection)
            await self._close(connection, reason="发送失败")
            return False

    async def is_online(self, session_id: str) -> bool:
        """会话是否在线"""
        async with self._lock:
            return session_id in self._connections

    async def count(self) -> int:
        """当前在线会话数"""
        async with self._lock:
            return len(self._connections)

    async def _sweep(self) -> None:
        """一轮心跳巡检：断开所有超时未活跃的连接"""
        timeout = self.config.heartbeatTimeout
        async with self._lock:
            stale = [
                connection for connection in self._connections.values()
                if connection.is_stale(timeout)
            ]
        for connection in stale:
            _log.warning(f"WS 心跳超时：session={connection.session_id}")
            await self.disconnect(connection)
            await self._close(connection, reason="心跳超时")

    async def _monitor_loop(self) -> None:
        """心跳巡检循环"""
        while True:
            try:
                await asyncio.sleep(self.config.heartbeatInterval)
                await self._sweep()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                # 巡检出错不应终止循环
                _log.warning(f"WS 心跳巡检出错：{e}")

    def start_monitor(self) -> None:
        """启动心跳巡检任务。需在事件循环内调用（应用启动时）"""
        if self._monitor is None or self._monitor.done():
            self._monitor = asyncio.create_task(self._monitor_loop())

    async def stop_monitor(self) -> None:
        """停止心跳巡检任务"""
        if self._monitor is None:
            return
        self._monitor.cancel()
        try:
            await self._monitor
        except asyncio.CancelledError:
            pass
        self._monitor = None

    async def shutdown(self) -> None:
        """关闭所有连接并停止巡检。应用退出时调用"""
        await self.stop_monitor()
        async with self._lock:
            connections = list(self._connections.values())
            self._connections.clear()
        for connection in connections:
            await self._close(connection, reason="服务关闭")


_manager: Optional[ConnectionManager] = None


def init_ws_manager(config: Optional[WebSocketConfig] = None) -> ConnectionManager:
    """初始化全局连接管理器。应在应用入口调用一次"""
    global _manager
    _manager = ConnectionManager(config=config)
    return _manager


def get_ws_manager() -> ConnectionManager:
    """获取全局连接管理器。未初始化时惰性初始化"""
    global _manager
    if _manager is None:
        _manager = ConnectionManager()
    return _manager
