"""WebSocket路由：连接握手、接收循环与消息分发"""

import asyncio
from typing import Awaitable, Callable, Optional

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from websocket.ws_config import get_ws_config
from websocket.ws_manager import Connection, get_ws_manager
from websocket.ws_message import MessageType, WSMessage, error_message
from error.errors import BaseError, WebSocketError
from util.log_util import LogUtil

_log = LogUtil()

router = APIRouter()

# 消息处理器：接收连接与消息，自行决定如何回复
Handler = Callable[[Connection, WSMessage], Awaitable[None]]
# 校验器：判断该会话是否允许接入
Validator = Callable[[str, Optional[str]], Awaitable[bool]]

_handlers: dict[MessageType, Handler] = {}
_validator: Optional[Validator] = None


def register_handler(messageType: MessageType, handler: Handler) -> None:
    """注册某类消息的处理器。由service层在应用启动时调用"""
    _handlers[messageType] = handler


def set_validator(validator: Optional[Validator]) -> None:
    """设置会话校验器。未设置时不做校验，任意session_id都能接入"""
    global _validator
    _validator = validator


async def _validate(websocket: WebSocket, session_id: str, token: Optional[str]) -> bool:
    """校验会话。不通过则关闭连接并返回False"""
    if _validator is None:
        return True
    try:
        allowed = await _validator(session_id, token)
    except Exception as e:
        # 校验器自身出错一律按拒绝处理，避免异常穿透导致连接悬挂
        allowed = False
        _log.warning(f"WS 会话校验异常：session={session_id} 原因={e}")
    if not allowed:
        # 1008 = Policy Violation，握手前拒绝无需先accept
        await websocket.close(code=1008, reason="会话校验失败")
        _log.warning(f"WS 会话校验失败：session={session_id}")
        return False
    return True


async def _dispatch(connection: Connection, message: WSMessage) -> None:
    """把消息交给对应处理器。未注册的类型回错误消息"""
    handler = _handlers.get(MessageType(message.type))
    if handler is None:
        await get_ws_manager().send(
            connection.session_id,
            error_message(f"暂不支持的消息类型：{message.type}", message.request_id),
        )
        return
    try:
        await handler(connection, message)
    except BaseError as e:
        # 业务异常回给客户端，连接保留
        _log.warning(f"WS 处理消息失败：type={message.type} 原因={e}")
        await get_ws_manager().send(
            connection.session_id,
            error_message(str(e), message.request_id),
        )


async def _parse(connection: Connection, raw: str) -> Optional[WSMessage]:
    """解析客户端文本。非法报文回错误消息并返回None"""
    config = get_ws_config()
    manager = get_ws_manager()
    if len(raw.encode("utf-8")) > config.maxMessageBytes:
        await manager.send(
            connection.session_id,
            error_message(f"消息超过{config.maxMessageBytes}字节上限"),
        )
        return None
    try:
        message = WSMessage.model_validate_json(raw)
    except ValidationError as e:
        await manager.send(
            connection.session_id,
            error_message(f"消息格式错误：{e.error_count()}处校验失败"),
        )
        return None
    # 会话归属以连接为准，不信任客户端自报
    message.session_id = connection.session_id
    return message


@router.websocket("/ws/{session_id}")
async def websocket_endpoint(
        websocket: WebSocket,
        session_id: str,
        token: Optional[str] = Query(None, description="校验令牌"),
    ) -> None:
    """游戏会话WebSocket入口：ws://host/ws/{session_id}"""
    if not await _validate(websocket, session_id, token):
        return

    manager = get_ws_manager()
    try:
        connection = await manager.connect(websocket, session_id)
    except WebSocketError as e:
        # connect内部已accept，这里用1013告知客户端稍后重试
        await websocket.close(code=1013, reason=str(e))
        return

    try:
        await manager.send(
            session_id,
            WSMessage(
                type=MessageType.CONNECTED,
                data={"session_id": session_id},
                session_id=session_id,
            ),
        )
        await _receive_loop(connection)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        _log.warning(f"WS 连接异常终止：session={session_id} 原因={e}")
    finally:
        await manager.disconnect(connection)


async def _receive_loop(connection: Connection) -> None:
    """接收循环。负责收包、解析、心跳应答与分发"""
    config = get_ws_config()
    manager = get_ws_manager()
    while True:
        try:
            # 超时上限略大于心跳超时，避免与巡检抢着关连接
            raw = await asyncio.wait_for(
                connection.websocket.receive_text(),
                timeout=config.heartbeatTimeout + config.heartbeatInterval,
            )
        except asyncio.TimeoutError:
            _log.warning(f"WS 读超时：session={connection.session_id}")
            return

        connection.touch()
        message = await _parse(connection, raw)
        if message is None:
            continue

        if MessageType(message.type) == MessageType.PING:
            await manager.send(
                connection.session_id,
                WSMessage(
                    type=MessageType.PONG,
                    session_id=connection.session_id,
                    request_id=message.request_id,
                ),
            )
            continue

        await _dispatch(connection, message)
