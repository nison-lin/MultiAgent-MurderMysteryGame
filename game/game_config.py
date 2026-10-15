"""游戏流程配置"""

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

from error.errors import BaseError, ConfigError

load_dotenv()

# 记忆存档的默认目录：项目根目录下的 logs/
_DEFAULT_LOG_DIR = str(Path(__file__).resolve().parent.parent / "logs")


def _int_env(name: str, default: int) -> int:
    """读取整数环境变量"""
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        raise ConfigError(f"{name}必须是整数")


def _float_env(name: str, default: float) -> float:
    """读取数值环境变量（秒），允许小数"""
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        raise ConfigError(f"{name}必须是数字")


class GameConfig:
    """游戏流程配置类。优先使用传入参数，未提供时从环境变量加载；时间单位均为秒"""

    def __init__(
            self,
            talkRounds: Optional[int] = None,
            aiTalkTimeout: Optional[float] = None,
            humanTalkTimeout: Optional[float] = None,
            privateDuration: Optional[float] = None,
            aiIdentifyTimeout: Optional[float] = None,
            humanIdentifyTimeout: Optional[float] = None,
            disconnectTimeout: Optional[float] = None,
            maxPrivateReplies: Optional[int] = None,
            logDir: Optional[str] = None,
        ):
        try:
            # 每章讨论的发言轮数，每轮所有角色按固定顺序各发言一次
            self.talkRounds = talkRounds if talkRounds is not None else _int_env("GAME_TALK_ROUNDS", 2)
            # 等待 AI 玩家发言的超时，超时跳过
            self.aiTalkTimeout = aiTalkTimeout if aiTalkTimeout is not None else _float_env("GAME_AI_TALK_TIMEOUT", 120)
            # 等待人类玩家发言的超时，超时跳过
            self.humanTalkTimeout = humanTalkTimeout if humanTalkTimeout is not None else _float_env("GAME_HUMAN_TALK_TIMEOUT", 180)
            # 每章私聊环节的时长
            self.privateDuration = privateDuration if privateDuration is not None else _float_env("GAME_PRIVATE_DURATION", 180)
            # 等待 AI 玩家指认凶手的超时
            self.aiIdentifyTimeout = aiIdentifyTimeout if aiIdentifyTimeout is not None else _float_env("GAME_AI_IDENTIFY_TIMEOUT", 180)
            # 等待人类玩家指认凶手的超时
            self.humanIdentifyTimeout = humanIdentifyTimeout if humanIdentifyTimeout is not None else _float_env("GAME_HUMAN_IDENTIFY_TIMEOUT", 300)
            # 人类玩家断线超过该时长则结束游戏
            self.disconnectTimeout = disconnectTimeout if disconnectTimeout is not None else _float_env("GAME_DISCONNECT_TIMEOUT", 300)
            # 每章私聊环节中，AI 玩家最多向同一个 AI 玩家发送的私聊条数
            self.maxPrivateReplies = maxPrivateReplies if maxPrivateReplies is not None else _int_env("GAME_MAX_PRIVATE_REPLIES", 3)
            # 记忆存档目录
            self.logDir = logDir or os.getenv("GAME_LOG_DIR", "").strip() or _DEFAULT_LOG_DIR

            if self.talkRounds <= 0:
                raise ConfigError("GAME_TALK_ROUNDS必须大于0")
            for name, value in (
                ("GAME_AI_TALK_TIMEOUT", self.aiTalkTimeout),
                ("GAME_HUMAN_TALK_TIMEOUT", self.humanTalkTimeout),
                ("GAME_PRIVATE_DURATION", self.privateDuration),
                ("GAME_AI_IDENTIFY_TIMEOUT", self.aiIdentifyTimeout),
                ("GAME_HUMAN_IDENTIFY_TIMEOUT", self.humanIdentifyTimeout),
                ("GAME_DISCONNECT_TIMEOUT", self.disconnectTimeout),
            ):
                if value <= 0:
                    raise ConfigError(f"{name}必须大于0")
            if self.maxPrivateReplies < 0:
                raise ConfigError("GAME_MAX_PRIVATE_REPLIES不能小于0")

        except BaseError:
            raise
        except Exception as e:
            raise ConfigError(f"游戏配置出错：{e}")
