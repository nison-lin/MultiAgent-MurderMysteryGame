"""自定义异常"""

class BaseError(Exception):
    """异常基类"""
    pass

class LLMError(BaseError):
    """LLM相关异常"""
    pass

class ConfigError(BaseError):
    """配置相关异常"""
    pass

class UserInputError(BaseError):
    """用户输入异常"""
    pass

class DataError(BaseError):
    """数据相关异常"""
    pass

class MiniMaxError(BaseError):
    """MiniMax相关异常"""
    pass

class OSSError(BaseError):
    """阿里云OSS相关异常"""
    pass

class StorageError(BaseError):
    """存储相关异常"""
    pass

class DatabaseError(BaseError):
    """数据库相关异常"""
    pass

class WebSocketError(BaseError):
    """WebSocket相关异常"""
    pass

class GameError(BaseError):
    """游戏流程相关异常"""
    pass