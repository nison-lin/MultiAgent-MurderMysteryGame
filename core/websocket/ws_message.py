"""WebSocket消息协议"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class MessageType(str, Enum):
    """消息类型。client_前缀为客户端发出，其余为服务端发出"""

    # 连接与心跳
    PING = "ping"
    PONG = "pong"
    CONNECTED = "connected"
    ERROR = "error"

    # 客户端动作
    CLIENT_ASK = "client_ask"            # 向某个角色提问
    CLIENT_ACTION = "client_action"      # 搜证、指认凶手等

    # 服务端推送
    CHARACTER_REPLY = "character_reply"  # 角色完整回复
    STREAM_DELTA = "stream_delta"        # 角色回复的流式增量
    STREAM_END = "stream_end"            # 一次流式回复结束
    GAME_EVENT = "game_event"            # 线索解锁、进入下一章等
    SESSION_STATE = "session_state"      # 当前进度快照


class WSMessage(BaseModel):
    """WebSocket消息体。收发两端统一使用该结构的JSON"""

    model_config = ConfigDict(use_enum_values=True, extra="ignore")

    type: MessageType = Field(..., description="消息类型")
    data: dict[str, Any] = Field(default_factory=dict, description="消息载荷")
    session_id: Optional[str] = Field(default=None, description="会话ID")
    character_id: Optional[int] = Field(default=None, description="相关角色ID：提问的对象或回话的角色")
    request_id: Optional[str] = Field(default=None, description="请求ID，用于把流式回复关联到一次提问")
    timestamp: datetime = Field(default_factory=datetime.now, description="消息时间")

    def to_json(self) -> str:
        """序列化为JSON字符串"""
        return self.model_dump_json(exclude_none=True)


def error_message(reason: str, request_id: Optional[str] = None) -> WSMessage:
    """构造一条错误消息"""
    return WSMessage(
        type=MessageType.ERROR,
        data={"reason": reason},
        request_id=request_id,
    )
