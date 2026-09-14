"""自定义异常"""

class LLMError(Exception):
    """LLM相关异常"""
    pass

class ConfigError(Exception):
    """配置相关异常"""
    pass

class UserInputError(Exception):
    """用户输入异常"""
    pass

class DataError(Exception):
    """数据相关异常"""
    pass

class MiniMaxError(Exception):
    """MiniMax相关异常"""
    pass

class OSSError(Exception):
    """阿里云OSS相关异常"""
    pass