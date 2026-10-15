"""游戏主持方：调度一局游戏从开始到结束的全部流程"""

import asyncio
import random
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

from agent.memory.accusation_memory import AccusationMemory
from agent.memory.discussion_memory import DiscussionMemory
from agent.memory.memory_enum import AgentTypeEnum
from agent.memory.memory_manager import MemoryManager
from agent.player_agent import PlayerAgent, assign_private_evidences
from client.llm_client import LLMClientWrapper
from db.entity.room_entity import PhaseEnum
from error.errors import BaseError, DataError, GameError
from game.game_config import GameConfig
from game.game_data import GameData, ScriptBundle
from game.game_state import Game, tally_votes, wait_for_message
from model.character import Character
from model.evidence import Evidence
from util.log_util import LogUtil
from util.uuid_util import create_uuid
from websocket.ws_channel import create_channel, remove_channel
from websocket.ws_manager import Connection, get_ws_manager
from websocket.ws_message import MessageType, WSMessage
from websocket.ws_router import register_handler

# 为 AI 角色创建 LLM 客户端，参数为角色
LLMFactory = Callable[[Character], LLMClientWrapper]

# 人类玩家离线时，检查其是否重连的间隔（秒）
_RECONNECT_CHECK_INTERVAL = 1.0


class GameHandler:
    """
    游戏主持方，不扮演任何角色，只负责推进阶段、转发人类玩家的消息、统计结果。

    每章流程（chapter 从 1 开始，直到某个角色的剧本 is_end 为真）：
        NEW_CHAPTER      广播进入新章节，向人类玩家推送本章剧本与背景故事
        SEARCH_EVIDENCE  广播进入搜证，用 SEND_EVIDENCE 向人类玩家推送公开证据与分给他的非公开证据
        TALK_TURN        按角色ID顺序进行若干轮发言，每次等待发言者的回应，超时或出错时跳过
        PRIVATE_START    私聊环节计时，结束后广播 PRIVATE_END 并推进轮次
    最终章私聊结束后广播 IDENTIFY_START，收齐指认后用 GAME_END 公布得票、被指认者与真凶。

    人类玩家的 TALK / PRIVATE_TALK / IDENTIFY 由主持方写入记忆后再经消息通道转发，
    不在对应环节时抛出 GameError，由路由层回复错误。整局流程在后台任务中运行，不阻塞消息接收。
    """

    def __init__(
        self,
        config: Optional[GameConfig] = None,
        data: Optional[GameData] = None,
        memory_manager: Optional[MemoryManager] = None,
        llm_factory: Optional[LLMFactory] = None,
    ):
        """
        :param config: 游戏流程配置，未提供时从环境变量加载
        :param data: 数据访问，未提供时读写数据库
        :param memory_manager: 记忆管理器，所有游戏共用
        :param llm_factory: 为 AI 角色创建 LLM 客户端，未提供时所有 AI 共用一个默认配置的客户端
        """
        self.config = config or GameConfig()
        self.data = data or GameData()
        self.memory_manager = memory_manager or MemoryManager()
        self._llm_factory = llm_factory
        self._default_llm: LLMClientWrapper | None = None
        # 会话ID -> 进行中的游戏
        self._games: dict[str, Game] = {}
        # 正在开始游戏的会话，防止同一会话重复开始
        self._starting: set[str] = set()
        self.logger = LogUtil()

    # ---------------- 生命周期 ----------------

    def register(self) -> None:
        """向 WebSocket 路由注册人类玩家的消息处理器"""
        register_handler(MessageType.START, self.on_start)
        register_handler(MessageType.TALK, self.on_talk)
        register_handler(MessageType.PRIVATE_TALK, self.on_private_talk)
        register_handler(MessageType.IDENTIFY, self.on_identify)
        register_handler(MessageType.PAUSE, self.on_pause)

    def get_game(self, session_id: str) -> Game | None:
        """会话对应的进行中的游戏"""
        return self._games.get(session_id)

    async def shutdown(self) -> None:
        """结束所有进行中的游戏。应用关闭时调用"""
        games = list(self._games.values())
        for game in games:
            if game.task is not None:
                game.task.cancel()
        await asyncio.gather(*(self._wait_end(game) for game in games))

    async def _wait_end(self, game: Game) -> None:
        """等待游戏的后台任务结束；任务未能完成清理时在此补做"""
        if game.task is not None:
            try:
                await game.task
            except (asyncio.CancelledError, Exception):
                pass
        await self._finish(game)

    # ---------------- 开始游戏 ----------------

    async def on_start(self, connection: Connection, message: WSMessage) -> None:
        """
        处理 START：data["script_id"] 为剧本ID，data["character_id"] 为人类玩家扮演的角色（可选，默认随机选择非凶手角色）。
        准备完成后回复 START，data 中带有游戏ID、人类玩家的角色与全部角色，然后在后台开始游戏流程。
        """
        session_id = connection.session_id
        if session_id in self._games or session_id in self._starting:
            raise GameError("当前会话已有进行中的游戏")
        if message.data.get("is_continue"):
            raise GameError("暂不支持继续游戏")
        script_id = self._parse_int(message.data.get("script_id"), "script_id")
        character_id = message.data.get("character_id")
        if character_id is not None:
            character_id = self._parse_int(character_id, "character_id")

        self._starting.add(session_id)
        try:
            bundle = self.data.load_script(script_id)
            self._check_characters(bundle.characters)
            human = self._pick_human(bundle.characters, character_id)
            room = self.data.create_room(script_id)
            if room.id is None:
                raise DataError("新建房间失败：没有房间ID")
            game = await self._setup(session_id, room.id, script_id, bundle, human)
        finally:
            self._starting.discard(session_id)

        self._games[session_id] = game
        await self._send_human(game, self._message(MessageType.START, self._start_data(game), message.request_id))
        game.task = asyncio.create_task(self._run(game))
        self.logger.log(f"游戏 {game.game_id} 开始：剧本={script_id} 人类玩家={game.human_role} AI玩家={list(game.agents)}")

    async def _setup(self, session_id: str, room_id: int, script_id: int, bundle: ScriptBundle, human: Character) -> Game:
        """创建记忆与消息通道，人类玩家加入通道，为其余角色启动 AI 玩家；失败时释放已创建的资源"""
        game_id = str(room_id)
        try:
            self.memory_manager.create_game(game_id)
        except BaseError:
            self._finish_room(room_id)
            raise
        try:
            channel = create_channel(game_id)
        except BaseError:
            self.memory_manager.remove_game(game_id)
            self._finish_room(room_id)
            raise

        game = Game(game_id, room_id, script_id, session_id, bundle, human, channel, channel.observe())
        try:
            self.memory_manager.load_character(game_id, human, game.human_role)
            channel.join_human(game.human_role, session_id)
            for character in bundle.characters:
                if character.id == human.id:
                    continue
                agent = PlayerAgent(
                    self.memory_manager, channel, character, self._llm_for(character), self.config.maxPrivateReplies
                )
                game.agents[agent.role_id] = agent
                agent.start()
        except Exception as e:
            await self._finish(game, save=False)
            if isinstance(e, BaseError):
                raise
            raise GameError(f"准备游戏失败：{e}")
        return game

    def _llm_for(self, character: Character) -> LLMClientWrapper:
        """AI 角色使用的 LLM 客户端"""
        if self._llm_factory is not None:
            return self._llm_factory(character)
        if self._default_llm is None:
            self._default_llm = LLMClientWrapper()
        return self._default_llm

    @staticmethod
    def _check_characters(characters: list[Character]) -> None:
        """角色需带有 id 与名称，角色名作为角色ID，不能重复"""
        if len(characters) < 2:
            raise DataError("剧本至少需要两个角色")
        if any(c.id is None or not c.name for c in characters):
            raise DataError("剧本中存在缺少 id 或名称的角色")
        names = [c.name for c in characters]
        if len(set(names)) != len(names):
            raise DataError("剧本中存在重名的角色")

    @staticmethod
    def _pick_human(characters: list[Character], character_id: int | None) -> Character:
        """人类玩家扮演的角色：指定时使用指定角色，否则随机选择一个非凶手角色"""
        if character_id is not None:
            human = next((c for c in characters if c.id == character_id), None)
            if human is None:
                raise GameError(f"角色 {character_id} 不属于该剧本")
            return human
        candidates = [c for c in characters if not c.is_murderer]
        if not candidates:
            raise DataError("剧本中没有可供人类玩家扮演的非凶手角色")
        return random.choice(candidates)

    @staticmethod
    def _parse_int(value: Any, name: str) -> int:
        if value is None or value == "":
            raise GameError(f"START 消息缺少 {name}")
        try:
            return int(value)
        except (TypeError, ValueError):
            raise GameError(f"{name} 必须是整数")

    @staticmethod
    def _start_data(game: Game) -> dict[str, Any]:
        """回复 START 的内容"""
        return {
            "game_id": game.game_id,
            "room_id": game.room_id,
            "script_id": game.script_id,
            "character_id": game.human.id,
            "role_id": game.human_role,
            "characters": [
                {"id": c.id, "name": c.name, "is_human": c.id == game.human.id} for c in game.characters
            ],
        }

    # ---------------- 游戏流程 ----------------

    async def _run(self, game: Game) -> None:
        """后台运行整局游戏，无论正常结束、出错还是被取消都会释放资源"""
        try:
            await self._play(game)
        except asyncio.CancelledError:
            self.logger.warning(f"游戏 {game.game_id} 被取消")
            raise
        except Exception as e:
            self.logger.warning(f"游戏 {game.game_id} 异常结束：{e}")
            await self._send_human(game, self._message(MessageType.ERROR, {"reason": f"游戏异常结束：{e}"}))
        finally:
            await self._finish(game)

    async def _play(self, game: Game) -> None:
        """逐章推进，最终章私聊结束后指认凶手"""
        is_end = False
        while not is_end:
            await self._checkpoint(game)
            is_end = await self._read(game, game.chapter + 1)
            for step in (self._search, self._discuss, self._private_chat):
                await self._checkpoint(game)
                await step(game)
        await self._checkpoint(game)
        await self._identify(game)

    async def _read(self, game: Game, chapter: int) -> bool:
        """进入新章节，向人类玩家推送本章剧本与背景故事；返回是否为最终章"""
        stories = {c.name: game.bundle.story_of(c.id, chapter) for c in game.characters}  # type: ignore[arg-type]
        if not any(stories.values()):
            raise GameError(f"剧本第{chapter}章没有任何角色的剧本，且之前没有出现最终章")
        endings = [role for role, story in stories.items() if story and story.is_end]
        if endings and len(endings) != len(stories):
            self.logger.warning(f"游戏 {game.game_id} 第{chapter}章只有{endings}的剧本是最终章，AI 玩家可能拒绝指认")
        is_end = bool(endings)

        game.chapter = chapter
        self._set_phase(game, PhaseEnum.READ)
        await game.channel.broadcast(self._message(MessageType.NEW_CHAPTER, {"chapter": chapter}), exclude=game.human_role)

        story = stories[game.human_role]
        if story is not None:
            self.memory_manager.add_story(game.game_id, game.human_role, story)
        backstory = game.bundle.backstory
        await self._send_human(game, self._message(MessageType.NEW_CHAPTER, {
            "chapter": chapter,
            "content": story.content if story else "",
            "is_end": is_end,
            "backstory": backstory.content if backstory else "",
        }))
        return is_end

    async def _search(self, game: Game) -> None:
        """搜证：AI 玩家自行读取证据；公开证据与分给人类玩家的证据由主持方推送并写入记忆"""
        self._set_phase(game, PhaseEnum.SEARCH)
        await game.channel.broadcast(self._message(MessageType.SEARCH_EVIDENCE, {"chapter": game.chapter}))

        evidences = self.data.load_evidences(game.script_id, game.chapter)
        public = [e for e in evidences if e.is_public]
        mine = assign_private_evidences(evidences, game.characters).get(game.human.id, [])  # type: ignore[arg-type]
        for evidence in public + mine:
            self.memory_manager.add_evidence(game.game_id, evidence, game.human_role)
        await self._send_human(game, self._message(MessageType.SEND_EVIDENCE, {
            "chapter": game.chapter,
            "public": [self._evidence_data(e) for e in public],
            "private": [self._evidence_data(e) for e in mine],
        }))

    @staticmethod
    def _evidence_data(evidence: Evidence) -> dict[str, Any]:
        return evidence.model_dump(mode="json", exclude={"created_at", "updated_at"}, exclude_none=True)

    async def _discuss(self, game: Game) -> None:
        """按角色ID顺序进行若干轮公开发言"""
        self._set_phase(game, PhaseEnum.TALK)
        for round_no in range(1, self.config.talkRounds + 1):
            for role in game.order:
                await self._talk_turn(game, role, round_no)

    async def _talk_turn(self, game: Game, role: str, round_no: int) -> None:
        """轮到某个角色发言，等待其回应；超时或出错时跳过"""
        is_human = role == game.human_role
        timeout = self.config.humanTalkTimeout if is_human else self.config.aiTalkTimeout
        request_id = create_uuid(MessageType.TALK_TURN)
        game.speaker, game.turn_request_id = role, request_id
        turn = self._message(MessageType.TALK_TURN, {"role_id": role, "round": round_no, "timeout": timeout}, request_id)
        await game.channel.broadcast(turn)

        # 人类玩家的发言转发时使用本次 TALK_TURN 的请求ID，与 AI 的回应统一匹配
        expected = (MessageType.TALK, MessageType.AGENT_TALK, MessageType.ERROR)
        reply = await wait_for_message(
            game.observer,
            lambda m: m.request_id == request_id and m.type in expected and m.data.get("from") == role,
            timeout,
            game.game_id,
        )
        game.speaker = game.turn_request_id = None
        if reply is None:
            self.logger.warning(f"游戏 {game.game_id} 第{game.chapter}章第{round_no}轮 {role} 发言超时，跳过")
        elif reply.type == MessageType.ERROR:
            self.logger.warning(f"游戏 {game.game_id} {role} 发言失败，跳过：{reply.data.get('reason')}")

    async def _private_chat(self, game: Game) -> None:
        """私聊环节计时结束后广播 PRIVATE_END，并推进到下一轮"""
        self._set_phase(game, PhaseEnum.PRIVATE)
        duration = self.config.privateDuration
        await game.channel.broadcast(self._message(MessageType.PRIVATE_START, {"duration": duration}))
        # 私聊消息由 AI 与人类玩家直接经通道收发，主持方只计时，期间的错误报告照常记录日志
        await wait_for_message(game.observer, lambda m: False, duration, game.game_id)
        game.phase = None
        await game.channel.broadcast(self._message(MessageType.PRIVATE_END))
        self.memory_manager.next_round(game.game_id)

    async def _identify(self, game: Game) -> None:
        """指认凶手：收齐所有玩家的指认（各自有超时），公布得票、被指认者与真凶"""
        request_id = create_uuid(MessageType.IDENTIFY_START)
        candidates = list(game.order)
        self._set_phase(game, PhaseEnum.IDENTIFY)
        game.identify_request_id, game.human_can_vote = request_id, True
        await game.channel.broadcast(self._message(MessageType.IDENTIFY_START, {
            "candidates": candidates,
            "timeout": self.config.humanIdentifyTimeout,
        }, request_id))

        votes = await self._collect_votes(game, request_id)
        game.phase, game.identify_request_id, game.human_can_vote = None, None, False
        result = tally_votes(votes, [c.name for c in game.characters if c.is_murderer])  # type: ignore[misc]
        self.logger.log(f"游戏 {game.game_id} 指认结果：{result}")
        await game.channel.broadcast(self._message(MessageType.GAME_END, result))

    async def _collect_votes(self, game: Game, request_id: str) -> dict[str, str]:
        """等待所有玩家的指认，每人有各自的截止时间；返回 投票人 -> 被指认者"""
        loop = asyncio.get_running_loop()
        deadlines = {
            role: loop.time() + (self.config.humanIdentifyTimeout if role == game.human_role else self.config.aiIdentifyTimeout)
            for role in game.order
        }
        expected = (MessageType.IDENTIFY, MessageType.AGENT_IDENTIFY, MessageType.ERROR)
        votes: dict[str, str] = {}
        while deadlines:
            reply = await wait_for_message(
                game.observer,
                lambda m: m.request_id == request_id and m.type in expected and m.data.get("from") in deadlines,
                min(deadlines.values()) - loop.time(),
                game.game_id,
            )
            if reply is None:
                now = loop.time()
                for role in [r for r, deadline in deadlines.items() if deadline <= now]:
                    deadlines.pop(role)
                    self.logger.warning(f"游戏 {game.game_id} {role} 指认超时")
                    if role == game.human_role:
                        game.human_can_vote = False
                continue
            role = reply.data["from"]
            deadlines.pop(role)
            if reply.type == MessageType.ERROR:
                self.logger.warning(f"游戏 {game.game_id} {role} 指认失败：{reply.data.get('reason')}")
            elif isinstance(reply.data.get("murderer"), str):
                votes[role] = reply.data["murderer"]
        return votes

    async def _checkpoint(self, game: Game) -> None:
        """
        阶段之间的检查点：暂停时在此等待恢复；人类玩家离线时等待其重连，离线超过 disconnectTimeout 则结束游戏。
        ConnectionManager 没有上下线通知，离线期间按固定间隔查询是否已重连。
        """
        loop = asyncio.get_running_loop()
        while True:
            online = await get_ws_manager().is_online(game.session_id)
            if online:
                game.offline_since = None
                if game.resume.is_set():
                    return
            else:
                game.offline_since = game.offline_since or loop.time()
                if loop.time() - game.offline_since >= self.config.disconnectTimeout:
                    raise GameError(f"人类玩家离线超过{self.config.disconnectTimeout}秒")
            if not online:
                await asyncio.sleep(_RECONNECT_CHECK_INTERVAL)
                continue
            # 暂停期间也要定期确认人类玩家仍在线
            try:
                await asyncio.wait_for(game.resume.wait(), _RECONNECT_CHECK_INTERVAL)
            except TimeoutError:
                pass

    def _set_phase(self, game: Game, phase: PhaseEnum) -> None:
        """更新主持方所处的环节，并同步到房间；房间记录写入失败不影响游戏进行"""
        game.phase = phase
        try:
            self.data.update_room(game.room_id, game.chapter, phase)
        except Exception as e:
            self.logger.warning(f"游戏 {game.game_id} 更新房间状态失败：{e}")

    async def _send_human(self, game: Game, message: WSMessage) -> bool:
        """把主持方的消息推送给人类玩家，人类玩家已离开通道时忽略"""
        try:
            return await game.channel.send(game.human_role, message)
        except BaseError as e:
            self.logger.warning(f"游戏 {game.game_id} 推送给人类玩家失败：{e}")
            return False

    @staticmethod
    def _message(message_type: MessageType, data: dict[str, Any] | None = None, request_id: str | None = None) -> WSMessage:
        """构造主持方发出的消息"""
        return WSMessage(type=message_type, data=data or {}, request_id=request_id or create_uuid(message_type))

    # ---------------- 人类玩家的消息 ----------------

    def _game_of(self, connection: Connection) -> Game:
        game = self._games.get(connection.session_id)
        if game is None or game.finished:
            raise GameError("当前会话没有进行中的游戏")
        return game

    async def on_talk(self, connection: Connection, message: WSMessage) -> None:
        """人类玩家公开发言，只在轮到他时有效：写入记忆后转发给其他玩家，并唤醒等待中的讨论流程"""
        game = self._game_of(connection)
        if game.phase != PhaseEnum.TALK or game.speaker != game.human_role or game.turn_request_id is None:
            raise GameError("现在没有轮到你发言")
        content = self._content(message)
        memory: DiscussionMemory = self.memory_manager.get_agent_memory(
            game.game_id, game.human_role, AgentTypeEnum.DISCUSSION)  # type: ignore[assignment]
        memory.add_speech(content)
        request_id, game.speaker = game.turn_request_id, None
        await game.channel.broadcast(
            self._human_message(game, MessageType.TALK, {"content": content}, request_id), exclude=game.human_role
        )

    async def on_private_talk(self, connection: Connection, message: WSMessage) -> None:
        """人类玩家私聊 AI 玩家，character_id 为对象角色：写入双方记忆后投递给对方，保留原请求ID供对方回复时使用"""
        game = self._game_of(connection)
        if game.phase != PhaseEnum.PRIVATE:
            raise GameError("现在不是私聊环节")
        target = game.role_of(message.character_id)
        if target not in game.agents:
            raise GameError("只能私聊 AI 玩家")
        content = self._content(message)
        self.memory_manager.record_private_chat(game.game_id, game.human_role, target, content)
        await game.channel.send(
            target, self._human_message(game, MessageType.PRIVATE_TALK, {"to": target, "content": content}, message.request_id)
        )

    async def on_identify(self, connection: Connection, message: WSMessage) -> None:
        """人类玩家指认凶手，character_id 为被指认的角色，每人一次：写入记忆后广播"""
        game = self._game_of(connection)
        if game.phase != PhaseEnum.IDENTIFY or game.identify_request_id is None:
            raise GameError("现在不是指认环节")
        if not game.human_can_vote:
            raise GameError("你已经指认过，或指认已超时")
        target = game.role_of(message.character_id)
        if target == game.human_role:
            raise GameError("不能指认自己")
        reason = str(message.data.get("content") or "").strip()
        memory: AccusationMemory = self.memory_manager.get_agent_memory(
            game.game_id, game.human_role, AgentTypeEnum.ACCUSATION)  # type: ignore[assignment]
        memory.cast_vote(target, reason)
        game.human_can_vote = False
        await game.channel.broadcast(
            self._human_message(game, MessageType.IDENTIFY, {"murderer": target, "content": reason}, game.identify_request_id),
            exclude=game.human_role,
        )

    async def on_pause(self, connection: Connection, message: WSMessage) -> None:
        """暂停或恢复游戏：data["paused"] 为目标状态，未提供时切换；在阶段之间生效，回复当前状态"""
        game = self._game_of(connection)
        paused = message.data.get("paused")
        if paused is None:
            paused = game.resume.is_set()
        if not isinstance(paused, bool):
            raise GameError("paused 必须是布尔值")
        if paused:
            game.resume.clear()
        else:
            game.resume.set()
        await self._send_human(game, self._message(MessageType.PAUSE, {"paused": paused}, message.request_id))

    def _human_message(self, game: Game, message_type: MessageType, data: dict[str, Any], request_id: str | None) -> WSMessage:
        """构造代人类玩家转发的消息"""
        return WSMessage(
            type=message_type,
            data={"from": game.human_role, **data},
            character_id=game.human.id,
            request_id=request_id or create_uuid(message_type),
        )

    @staticmethod
    def _content(message: WSMessage) -> str:
        content = str(message.data.get("content") or "").strip()
        if not content:
            raise GameError(f"{message.type} 消息缺少 content")
        return content

    # ---------------- 结束与清理 ----------------

    async def _finish(self, game: Game, save: bool = True) -> None:
        """释放一局游戏的全部资源，只执行一次；每一步失败都不影响后续步骤"""
        if game.finished:
            return
        game.finished = True
        game.resume.set()
        for role, agent in game.agents.items():
            try:
                await agent.stop()
            except Exception as e:
                self.logger.warning(f"游戏 {game.game_id} 停止 AI 玩家 {role} 失败：{e}")
        game.channel.unobserve(game.observer)
        remove_channel(game.game_id)
        if save:
            try:
                path = Path(self.config.logDir) / f"game_{game.game_id}_{datetime.now():%Y%m%d%H%M%S}.json"
                self.memory_manager.save(game.game_id, path)
                self.logger.log(f"游戏 {game.game_id} 的记忆已保存到 {path}")
            except Exception as e:
                self.logger.warning(f"游戏 {game.game_id} 保存记忆失败：{e}")
        self.memory_manager.remove_game(game.game_id)
        self._finish_room(game.room_id)
        if self._games.get(game.session_id) is game:
            del self._games[game.session_id]
        self.logger.log(f"游戏 {game.game_id} 已结束")

    def _finish_room(self, room_id: int) -> None:
        try:
            self.data.finish_room(room_id)
        except Exception as e:
            self.logger.warning(f"房间 {room_id} 标记结束失败：{e}")


_handler: Optional[GameHandler] = None


def init_game_handler(**kwargs: Any) -> GameHandler:
    """初始化全局游戏主持方并注册消息处理器。应在应用入口调用一次"""
    global _handler
    _handler = GameHandler(**kwargs)
    _handler.register()
    return _handler


def get_game_handler() -> GameHandler:
    """获取全局游戏主持方。未初始化时惰性初始化"""
    global _handler
    if _handler is None:
        return init_game_handler()
    return _handler

