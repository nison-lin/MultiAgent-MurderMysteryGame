"""核心模块：WebSocket通信与应用装配"""

from .app import app, create_app
from .websocket.ws_config import WebSocketConfig, get_ws_config, init_ws_config
from .websocket.ws_manager import Connection, ConnectionManager, get_ws_manager, init_ws_manager
from .websocket.ws_message import MessageType, WSMessage, error_message
from .websocket.ws_router import register_handler, router, set_validator

__all__ = [
    "app",
    "create_app",
    "WebSocketConfig",
    "get_ws_config",
    "init_ws_config",
    "Connection",
    "ConnectionManager",
    "get_ws_manager",
    "init_ws_manager",
    "MessageType",
    "WSMessage",
    "error_message",
    "register_handler",
    "router",
    "set_validator",
]
