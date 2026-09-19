"""异常模块"""

from .errors import (
    BaseError,
    LLMError,
    ConfigError,
    UserInputError,
    DataError,
    MiniMaxError,
    OSSError,
    StorageError,
    DatabaseError,
    WebSocketError
)

__all__ = [
    "BaseError",
    "LLMError",
    "ConfigError",
    "UserInputError",
    "DataError",
    "MiniMaxError",
    "OSSError",
    "StorageError",
    "DatabaseError",
    "WebSocketError"
]
