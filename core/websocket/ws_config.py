"""WebSocket配置"""

import os
from typing import Optional

from dotenv import load_dotenv

from error.errors import BaseError, ConfigError

load_dotenv()


def _int_env(name: str, default: int) -> int:
    """读取整数环境变量"""
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        raise ConfigError(f"{name}必须是整数")


class WebSocketConfig:
    """WebSocket配置类。优先使用传入参数，未提供时从环境变量加载"""

    def __init__(
            self,
            path: Optional[str] = None,
            heartbeatInterval: Optional[int] = None,
            heartbeatTimeout: Optional[int] = None,
            maxConnections: Optional[int] = None,
            maxMessageBytes: Optional[int] = None,
            sendTimeout: Optional[int] = None,
        ):
        try:
            self.path = path or os.getenv("WS_PATH", "").strip() or "/ws/{session_id}"
            # 心跳间隔：服务端巡检间隔（秒）
            self.heartbeatInterval = heartbeatInterval or _int_env("WS_HEARTBEAT_INTERVAL", 30)
            # 心跳超时：超过该时长未收到任何消息则断开（秒）
            self.heartbeatTimeout = heartbeatTimeout or _int_env("WS_HEARTBEAT_TIMEOUT", 90)
            # 同时在线会话上限，防止连接无上限增长
            self.maxConnections = maxConnections or _int_env("WS_MAX_CONNECTIONS", 32)
            # 单条消息最大字节数，超出直接拒绝
            self.maxMessageBytes = maxMessageBytes or _int_env("WS_MAX_MESSAGE_BYTES", 65536)
            # 单次发送超时（秒），防止慢客户端拖住广播
            self.sendTimeout = sendTimeout or _int_env("WS_SEND_TIMEOUT", 10)

            if self.heartbeatTimeout <= self.heartbeatInterval:
                raise ConfigError("WS_HEARTBEAT_TIMEOUT必须大于WS_HEARTBEAT_INTERVAL")
            if self.maxConnections <= 0:
                raise ConfigError("WS_MAX_CONNECTIONS必须大于0")

        except BaseError:
            raise
        except Exception as e:
            raise ConfigError(f"WebSocket配置出错：{e}")


_config: Optional[WebSocketConfig] = None


def init_ws_config(**kwargs) -> WebSocketConfig:
    """初始化全局WebSocket配置。应在应用入口调用一次"""
    global _config
    _config = WebSocketConfig(**kwargs)
    return _config


def get_ws_config() -> WebSocketConfig:
    """获取全局WebSocket配置。未初始化时按环境变量惰性初始化"""
    global _config
    if _config is None:
        _config = WebSocketConfig()
    return _config
