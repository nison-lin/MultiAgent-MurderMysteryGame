"""记忆模块枚举"""

from enum import Enum


class MemoryTypeEnum(str, Enum):
    """记忆时效"""
    SHORT_TERM = "short_term"  # 短期记忆：仅在当前轮次有效，轮次结束时清除
    LONG_TERM = "long_term"    # 长期记忆：整局游戏持续保留


class VisibilityEnum(str, Enum):
    """记忆可见性"""
    PRIVATE = "private"  # 私有记忆：仅所属角色可见
    PUBLIC = "public"    # 公共记忆：同一局游戏的所有角色可见


class MemoryCategoryEnum(str, Enum):
    """记忆内容类别，值同时作为摘要中的展示名称"""
    IDENTITY = "角色身份"
    SCRIPT = "剧本"
    EVIDENCE = "证据"
    SPEECH = "公开发言"
    PRIVATE_CHAT = "私聊"
    ANNOUNCEMENT = "系统公告"
    VOTE = "投票"
    FOCUS = "讨论焦点"
    OPINION = "他人观点"
    NOTE = "笔记"


class AgentTypeEnum(str, Enum):
    """Agent类型，每种类型对应一种记忆实现"""
    DISCUSSION = "discussion"
    PRIVATE_CHAT = "private_chat"
    ACCUSATION = "accusation"
