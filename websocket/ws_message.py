"""WebSocket消息协议"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from util.uuid_util import create_uuid


class MessageType(str, Enum):
    """消息类型。client_前缀为客户端发出，其余为服务端发出"""

    # 连接与心跳
    PING = "ping"
    PONG = "pong"
    CONNECTED = "connected"
    ERROR = "error"

    # 客户端动作
    START = "start"                      # 开始游戏
    TALK = "talk"                        # 发送讨论消息
    PRIVATE_TALK = "private_talk"        # 私聊讨论
    IDENTIFY = "identify"                # 指认凶手
    PAUSE = "pause"                      # 暂停游戏

    # 服务端推送
    AGENT_TALK = "agent_talk"            # agent发送讨论消息
    STREAM_TALK = "stream_talk"          # agent流式发送讨论消息
    AGENT_PRIVATE = "agent_private"      # agent回复私聊
    STREAM_PRIVATE = "stream_private"    # agent流式回复私聊
    STREAM_END = "stream_end"            # 一次流式回复结束
    AGENT_IDENTIFY = "agent_identify"    # agent指认凶手
    NEW_CHAPTER = "new_chapter"          # 进入下一章
    SEND_EVIDENCE = "send_evidence"      # 发送证据

    # 主持方推送的游戏阶段
    SEARCH_EVIDENCE = "search_evidence"  # 进入搜证环节
    TALK_TURN = "talk_turn"              # 轮到某个角色公开发言
    PRIVATE_START = "private_start"      # 私聊环节开始
    PRIVATE_END = "private_end"          # 私聊环节结束
    IDENTIFY_START = "identify_start"    # 指认凶手环节开始


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


def error_message(reason: str, request_id: str|None = None) -> WSMessage:
    """构造一条错误消息"""
    return WSMessage(
        type=MessageType.ERROR,
        data={"reason": reason},
        request_id=request_id or create_uuid(MessageType.ERROR),
    )

def start_message(script_id: int, room_id: int|None = None, request_id: str|None = None):
    """构建一条开始游戏消息"""
    is_continue = room_id is not None
    data: dict[str, Any] = {"is_continue": is_continue}
    if is_continue:
        data["room_id"] = room_id
    else:
        data["script_id"] = script_id
    return WSMessage(
        type=MessageType.START,
        data=data,
        request_id=request_id or create_uuid(MessageType.START)
    )