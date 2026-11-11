"""游戏流程状态机：用 LangGraph 管理一局游戏的阶段转移"""

import asyncio
from typing import TYPE_CHECKING, Any, Literal, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from agent.player_agent import assign_private_evidences
from db.entity.room_entity import PhaseEnum
from error.errors import GameError
from game.game_state import Game, tally_votes, wait_for_message
from model.evidence import Evidence
from util.uuid_util import create_uuid
from websocket.ws_manager import get_ws_manager
from websocket.ws_message import MessageType

if TYPE_CHECKING:
    from game.game_handler import GameHandler

# 人类玩家离线时，检查其是否重连的间隔（秒）
_RECONNECT_CHECK_INTERVAL = 1.0

# 每章经过的图步数：4 个阶段节点，每个之前各经过一次 gate
_STEPS_PER_CHAPTER = 8

Stage = Literal["read", "search", "discuss", "private", "identify"]
_STAGES: list[Stage] = ["read", "search", "discuss", "private", "identify"]


class FlowState(TypedDict):
    """状态机中流转的流程数据；运行时对象（通道、AI 玩家等）经 config 传入，不放在状态中"""
    # 当前章节，0 表示尚未开始
    chapter: int
    # 当前章节是否为最终章
    is_end: bool
    # gate 之后进入的阶段
    next: Stage
    # 指认结果，即 GAME_END 的内容
    result: dict[str, Any] | None


class GameFlow:
    """
    一局游戏的阶段状态机，图结构如下（所有游戏共用一张编译好的图，每局的 Game 经 config 传入）：

        START -> gate -(next)-> read | search | discuss | private | identify
        read -> gate        next = search
        search -> gate      next = discuss
        discuss -> gate     next = private
        private -> gate     next = identify（最终章）或 read（下一章）
        identify -> END

    gate 是阶段之间的检查点：暂停时等待恢复，人类玩家离线时等待重连，离线超时则结束游戏。
    """

    def __init__(self, handler: "GameHandler"):
        """
        :param handler: 游戏主持方，复用其配置、数据访问、记忆管理与消息发送
        """
        self.handler = handler
        self.graph = self.build()

    def build(self) -> CompiledStateGraph:
        """构建并编译状态机"""
        graph = StateGraph(FlowState)
        graph.add_node("gate", self.gate)
        graph.add_node("read", self.read)
        graph.add_node("search", self.search)
        graph.add_node("discuss", self.discuss)
        graph.add_node("private", self.private)
        graph.add_node("identify", self.identify)

        graph.add_edge(START, "gate")
        graph.add_conditional_edges("gate", lambda state: state["next"], _STAGES)
        for stage in ("read", "search", "discuss", "private"):
            graph.add_edge(stage, "gate")
        graph.add_edge("identify", END)
        return graph.compile()

    async def run(self, game: Game) -> FlowState:
        """从第一章开始运行整局游戏，返回最终状态"""
        initial: FlowState = {"chapter": 0, "is_end": False, "next": "read", "result": None}
        chapters = [s.chapter or 0 for stories in game.bundle.stories.values() for s in stories]
        config: RunnableConfig = {
            "configurable": {"game": game},
            # 默认上限 25 步只够 3 章；多留余量给超出最后一章时 read 报错及指认
            "recursion_limit": _STEPS_PER_CHAPTER * max(chapters, default=1) + 10,
        }
        return await self.graph.ainvoke(initial, config=config)  # type: ignore[return-value]

    @staticmethod
    def _game(config: RunnableConfig) -> Game:
        return config["configurable"]["game"]

    # ---------------- 节点 ----------------

    async def gate(self, state: FlowState, config: RunnableConfig) -> dict[str, Any]:
        """
        阶段之间的检查点：暂停时在此等待恢复；人类玩家离线时等待其重连，离线超过 disconnectTimeout 则结束游戏。
        ConnectionManager 没有上下线通知，离线期间按固定间隔查询是否已重连。
        """
        game = self._game(config)
        timeout = self.handler.config.disconnectTimeout
        loop = asyncio.get_running_loop()
        while True:
            online = await get_ws_manager().is_online(game.session_id)
            if online:
                game.offline_since = None
                if game.resume.is_set():
                    return {}
            else:
                game.offline_since = game.offline_since or loop.time()
                if loop.time() - game.offline_since >= timeout:
                    raise GameError(f"人类玩家离线超过{timeout}秒")
            if not online:
                await asyncio.sleep(_RECONNECT_CHECK_INTERVAL)
                continue
            # 暂停期间也要定期确认人类玩家仍在线
            try:
                await asyncio.wait_for(game.resume.wait(), _RECONNECT_CHECK_INTERVAL)
            except TimeoutError:
                pass

    async def read(self, state: FlowState, config: RunnableConfig) -> dict[str, Any]:
        """进入新章节，向人类玩家推送本章剧本与背景故事，并记录本章是否为最终章"""
        handler, game = self.handler, self._game(config)
        chapter = state["chapter"] + 1
        stories = {c.name: game.bundle.story_of(c.id, chapter) for c in game.characters}  # type: ignore[arg-type]
        if not any(stories.values()):
            raise GameError(f"剧本第{chapter}章没有任何角色的剧本，且之前没有出现最终章")
        endings = [role for role, story in stories.items() if story and story.is_end]
        if endings and len(endings) != len(stories):
            handler.logger.warning(f"游戏 {game.game_id} 第{chapter}章只有{endings}的剧本是最终章，AI 玩家可能拒绝指认")
        is_end = bool(endings)

        game.chapter = chapter
        handler._set_phase(game, PhaseEnum.READ)
        await game.channel.broadcast(handler._message(MessageType.NEW_CHAPTER, {"chapter": chapter}), exclude=game.human_role)

        story = stories[game.human_role]
        if story is not None:
            handler.memory_manager.add_story(game.game_id, game.human_role, story)
        backstory = game.bundle.backstory
        await handler._send_human(game, handler._message(MessageType.NEW_CHAPTER, {
            "chapter": chapter,
            "content": story.content if story else "",
            "is_end": is_end,
            "backstory": backstory.content if backstory else "",
        }))
        return {"chapter": chapter, "is_end": is_end, "next": "search"}

    async def search(self, state: FlowState, config: RunnableConfig) -> dict[str, Any]:
        """搜证：AI 玩家自行读取证据；公开证据与分给人类玩家的证据由主持方推送并写入记忆"""
        handler, game = self.handler, self._game(config)
        handler._set_phase(game, PhaseEnum.SEARCH)
        await game.channel.broadcast(handler._message(MessageType.SEARCH_EVIDENCE, {"chapter": game.chapter}))

        evidences = handler.data.load_evidences(game.script_id, game.chapter)
        public = [e for e in evidences if e.is_public]
        mine = assign_private_evidences(evidences, game.characters).get(game.human.id, [])  # type: ignore[arg-type]
        for evidence in public + mine:
            handler.memory_manager.add_evidence(game.game_id, evidence, game.human_role)
        await handler._send_human(game, handler._message(MessageType.SEND_EVIDENCE, {
            "chapter": game.chapter,
            "public": [self._evidence_data(e) for e in public],
            "private": [self._evidence_data(e) for e in mine],
        }))
        return {"next": "discuss"}

    async def discuss(self, state: FlowState, config: RunnableConfig) -> dict[str, Any]:
        """按角色ID顺序进行若干轮公开发言"""
        game = self._game(config)
        self.handler._set_phase(game, PhaseEnum.TALK)
        for round_no in range(1, self.handler.config.talkRounds + 1):
            for role in game.order:
                await self._talk_turn(game, role, round_no)
        return {"next": "private"}

    async def private(self, state: FlowState, config: RunnableConfig) -> dict[str, Any]:
        """私聊环节计时结束后广播 PRIVATE_END，并推进轮次；最终章之后进入指认，否则进入下一章"""
        handler, game = self.handler, self._game(config)
        handler._set_phase(game, PhaseEnum.PRIVATE)
        duration = handler.config.privateDuration
        await game.channel.broadcast(handler._message(MessageType.PRIVATE_START, {"duration": duration}))
        # 私聊消息由 AI 与人类玩家直接经通道收发，主持方只计时，期间的错误报告照常记录日志
        await wait_for_message(game.observer, lambda m: False, duration, game.game_id)
        game.phase = None
        await game.channel.broadcast(handler._message(MessageType.PRIVATE_END))
        handler.memory_manager.next_round(game.game_id)
        return {"next": "identify" if state["is_end"] else "read"}

    async def identify(self, state: FlowState, config: RunnableConfig) -> dict[str, Any]:
        """指认凶手：收齐所有玩家的指认（各自有超时），公布得票、被指认者与真凶"""
        handler, game = self.handler, self._game(config)
        request_id = create_uuid(MessageType.IDENTIFY_START)
        candidates = list(game.order)
        handler._set_phase(game, PhaseEnum.IDENTIFY)
        game.identify_request_id, game.human_can_vote = request_id, True
        await game.channel.broadcast(handler._message(MessageType.IDENTIFY_START, {
            "candidates": candidates,
            "timeout": handler.config.humanIdentifyTimeout,
        }, request_id))

        votes = await self._collect_votes(game, request_id)
        game.phase, game.identify_request_id, game.human_can_vote = None, None, False
        result = tally_votes(votes, [c.name for c in game.characters if c.is_murderer])  # type: ignore[misc]
        handler.logger.log(f"游戏 {game.game_id} 指认结果：{result}")
        await game.channel.broadcast(handler._message(MessageType.GAME_END, result))
        return {"result": result}

    # ---------------- 节点内部步骤 ----------------

    async def _talk_turn(self, game: Game, role: str, round_no: int) -> None:
        """轮到某个角色发言，等待其回应；超时或出错时跳过"""
        handler = self.handler
        is_human = role == game.human_role
        timeout = handler.config.humanTalkTimeout if is_human else handler.config.aiTalkTimeout
        request_id = create_uuid(MessageType.TALK_TURN)
        game.speaker, game.turn_request_id = role, request_id
        turn = handler._message(MessageType.TALK_TURN, {"role_id": role, "round": round_no, "timeout": timeout}, request_id)
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
            handler.logger.warning(f"游戏 {game.game_id} 第{game.chapter}章第{round_no}轮 {role} 发言超时，跳过")
        elif reply.type == MessageType.ERROR:
            handler.logger.warning(f"游戏 {game.game_id} {role} 发言失败，跳过：{reply.data.get('reason')}")

    async def _collect_votes(self, game: Game, request_id: str) -> dict[str, str]:
        """等待所有玩家的指认，每人有各自的截止时间；返回 投票人 -> 被指认者"""
        handler = self.handler
        loop = asyncio.get_running_loop()
        deadlines = {
            role: loop.time() + (
                handler.config.humanIdentifyTimeout if role == game.human_role else handler.config.aiIdentifyTimeout
            )
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
                    handler.logger.warning(f"游戏 {game.game_id} {role} 指认超时")
                    if role == game.human_role:
                        game.human_can_vote = False
                continue
            role = reply.data["from"]
            deadlines.pop(role)
            if reply.type == MessageType.ERROR:
                handler.logger.warning(f"游戏 {game.game_id} {role} 指认失败：{reply.data.get('reason')}")
            elif isinstance(reply.data.get("murderer"), str):
                votes[role] = reply.data["murderer"]
        return votes

    @staticmethod
    def _evidence_data(evidence: Evidence) -> dict[str, Any]:
        return evidence.model_dump(mode="json", exclude={"created_at", "updated_at"}, exclude_none=True)
