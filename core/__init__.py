"""核心模块：WebSocket通信与应用装配"""

from .app import app, create_app

__all__ = [
    "app",
    "create_app",
]
