"""玩家 Agent"""

import asyncio
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, List, Optional, Sequence, Tuple

from client.llm_client import LLMClientWrapper
from agent.accusation_agent import Accusation, AccusationAgent
from agent.discussion_agent import DiscussionAgent
from agent.memory.memory_enum import MemoryCategoryEnum
from agent.memory.memory_manager import MemoryManager
from agent.private_chat_agent import PrivateChatAgent
from db.database import get_session
from db.repository import ScriptRepository, StoryRepository
from error.errors import DataError, GameError
from model.character import Character
from model.evidence import Evidence
from model.story import Story
from util.log_util import LogUtil
from util.uuid_util import create_uuid
from websocket.ws_channel import GameChannel
from websocket.ws_message import MessageType, WSMessage, error_message


class PlayerPhaseEnum(str, Enum):
    """玩家在当前章节所处的环节"""
    IDLE = "未开始"
    READ = "阅读剧本"
    SEARCH = "搜证"
    DISCUSS = "讨论"
    PRIVATE_CHAT = "私聊"
    PRIVATE_DONE = "私聊结束"
    ACCUSED = "已指认凶手"


# 进入某个环节前允许所处的环节：每章按 剧本 -> 搜证 -> 讨论 -> 私聊 的顺序行动，最终章私聊结束后指认凶手。
# 讨论有多轮发言，因此允许从讨论再次进入讨论
_ALLOWED_FROM: Dict[PlayerPhaseEnum, set[PlayerPhaseEnum]] = {
    PlayerPhaseEnum.READ: {PlayerPhaseEnum.IDLE, PlayerPhaseEnum.PRIVATE_DONE},
    PlayerPhaseEnum.SEARCH: {PlayerPhaseEnum.READ},
    PlayerPhaseEnum.DISCUSS: {PlayerPhaseEnum.SEARCH, PlayerPhaseEnum.DISCUSS},
    PlayerPhaseEnum.PRIVATE_CHAT: {PlayerPhaseEnum.DISCUSS},
    PlayerPhaseEnum.PRIVATE_DONE: {PlayerPhaseEnum.PRIVATE_CHAT},
    PlayerPhaseEnum.ACCUSED: {PlayerPhaseEnum.PRIVATE_DONE},
}

MessageHandler = Callable[[WSMessage], Awaitable[None]]


def assign_private_evidences(evidences: Sequence[Evidence], characters: Sequence[Character]) -> Dict[int, List[Evidence]]:
    """
    把非公开证据轮流分配给各角色：角色与证据都按ID排序后依次分配，起始角色随章节轮换，
    避免证据较少时总是同一个角色先拿到。人类玩家也应按此规则发放，保证与 AI 玩家拿到的证据一致。
    :return: 角色ID -> 分到的证据
    """
    owners = sorted(c.id for c in characters if c.id is not None)
    result: Dict[int, List[Evidence]] = {owner: [] for owner in owners}
    if not owners:
        return result
    private = sorted((e for e in evidences if not e.is_public), key=lambda e: e.id or 0)
    for i, evidence in enumerate(private):
        result[owners[(i + (evidence.chapter or 0)) % len(owners)]].append(evidence)
    return result


class PlayerAgent:
    """
    剧本杀玩家 Agent，扮演一个角色，接受主持方的调度，把每个环节交给对应的子 Agent 完成。

    行动顺序（由主持方经消息通道推送阶段消息驱动，本 Agent 校验顺序，乱序的消息会被拒绝）：
        NEW_CHAPTER      读取本章本角色的剧本，写入私有记忆
        SEARCH_EVIDENCE  读取本章证据：公开证据写入公共记忆，非公开证据按 assign_private_evidences 分到的写入私有记忆
        TALK_TURN        轮到本角色时调用讨论 Agent 发言，并广播 AGENT_TALK
        PRIVATE_START    调用私聊 Agent 判断是否主动私聊，需要时发出 AGENT_PRIVATE；
                         私聊环节内收到的私聊由私聊 Agent 回复，对 AI 玩家的回复条数受 max_private_replies 限制，防止无限往复
        PRIVATE_END      结束私聊
        IDENTIFY_START   最终章私聊结束后调用指认凶手 Agent，广播 AGENT_IDENTIFY

    记忆：通过 MemoryManager 只读写本角色的记忆，三个子 Agent 共享本角色的长期私有记忆，短期记忆各自独立。
          发言、私聊、投票由发送方写入记忆后再经通道投递，因此收到他人的发言时无需重复写入；
          轮次推进（next_round）由主持方负责。
    互动：与其他玩家的所有互动都经 GameChannel 收发，处理失败时向观察者（主持方）报告错误。
    """

    def __init__(
        self,
        memory_manager: MemoryManager,
        channel: GameChannel,
        character: Character,
        llm: Optional[LLMClientWrapper] = None,
        max_private_replies: int = 3,
    ):
        """
        :param memory_manager: 记忆管理器，同一局游戏的所有玩家共用
        :param channel: 本局游戏的消息通道
        :param character: 扮演的角色，需已存储（带有 id 与 script_id），角色名作为角色ID
        :param llm: 三个子 Agent 共用的 LLM 客户端，未提供时使用默认配置创建
        :param max_private_replies: 每章私聊环节中，最多向同一个 AI 玩家发送的私聊条数
        """
        if character.id is None or character.script_id is None or not character.name:
            raise DataError("角色需要已存储，并带有名称、id 与 script_id")
        self.memory_manager = memory_manager
        self.channel = channel
        self.character = character
        self.game_id = channel.game_id
        self.role_id = character.name
        self.character_id: int = character.id
        self.script_id: int = character.script_id
        self.max_private_replies = max_private_replies
        self.name = f"{self.role_id}-player"
        self.logger = LogUtil()

        llm = llm or LLMClientWrapper()
        self.private_chat = PrivateChatAgent(memory_manager, self.game_id, self.role_id, llm)
        self.discussion = DiscussionAgent(memory_manager, self.game_id, self.role_id, llm)
        self.accusation = AccusationAgent(memory_manager, self.game_id, self.role_id, llm)

        self.phase = PlayerPhaseEnum.IDLE
        self.chapter = 0
        self.is_final_chapter = False
        self.result: Accusation | None = None
        # 本章私聊环节中向各角色发出的私聊条数
        self._sent_private: Dict[str, int] = {}
        self._task: asyncio.Task | None = None
        self._handlers: Dict[MessageType, MessageHandler] = {
            MessageType.NEW_CHAPTER: self._on_new_chapter,
            MessageType.SEARCH_EVIDENCE: self._on_search_evidence,
            MessageType.TALK_TURN: self._on_talk_turn,
            MessageType.TALK: self._on_speech,
            MessageType.AGENT_TALK: self._on_speech,
            MessageType.PRIVATE_START: self._on_private_start,
            MessageType.PRIVATE_TALK: self._on_private_message,
            MessageType.AGENT_PRIVATE: self._on_private_message,
            MessageType.PRIVATE_END: self._on_private_end,
            MessageType.IDENTIFY_START: self._on_identify_start,
            MessageType.IDENTIFY: self._on_speech,
            MessageType.AGENT_IDENTIFY: self._on_speech,
        }

    # ---------------- 生命周期 ----------------

    def start(self) -> None:
        """写入角色身份、加入消息通道并开始处理消息。需在事件循环内调用，且主持方已调用 memory_manager.create_game"""
        if self._task is not None and not self._task.done():
            return
        self._load_identity()
        inbox = self.channel.join_agent(self.role_id)
        self._task = asyncio.create_task(self._run(inbox))

    async def stop(self) -> None:
        """停止处理消息并离开消息通道"""
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        self.channel.leave(self.role_id)

    async def _run(self, inbox: asyncio.Queue[WSMessage]) -> None:
        """按到达顺序逐条处理消息，单条消息处理失败不会终止循环"""
        while True:
            message = await inbox.get()
            try:
                await self.handle(message)
            except Exception as e:
                self.logger.warning(f"[{self.name}] 处理消息失败：type={message.type} 原因={e}")
                error = error_message(f"{self.role_id}处理{message.type}失败：{e}", message.request_id)
                error.data["from"] = self.role_id
                error.character_id = self.character_id
                self.channel.notify(error)

    async def handle(self, message: WSMessage) -> None:
        """处理一条消息，与本玩家无关的消息类型直接忽略"""
        handler = self._handlers.get(MessageType(message.type))
        if handler is not None:
            await handler(message)

    # ---------------- 各环节 ----------------

    async def _on_new_chapter(self, message: WSMessage) -> None:
        """进入新章节，读取本角色本章的剧本"""
        if self.is_final_chapter:
            raise GameError(f"[{self.name}] 已经是最终章，不能进入新章节")
        self._check_phase(PlayerPhaseEnum.READ)
        chapter = int(self._require(message, "chapter"))
        if chapter <= self.chapter:
            raise GameError(f"[{self.name}] 章节 {chapter} 不在当前章节 {self.chapter} 之后")

        story = self._load_story(chapter)
        if story is None:
            self.logger.warning(f"[{self.name}] 角色在第{chapter}章没有剧本")
        else:
            self.memory_manager.add_story(self.game_id, self.role_id, story)
        self.chapter = chapter
        self.is_final_chapter = bool(story and story.is_end)
        self.phase = PlayerPhaseEnum.READ

    async def _on_search_evidence(self, message: WSMessage) -> None:
        """搜证：读取本章证据，公开证据写入公共记忆，分给本角色的非公开证据写入私有记忆"""
        self._check_phase(PlayerPhaseEnum.SEARCH)
        evidences, characters = self._load_evidences()
        mine = assign_private_evidences(evidences, characters).get(self.character_id, [])
        for evidence in [e for e in evidences if e.is_public] + mine:
            self.memory_manager.add_evidence(self.game_id, evidence, self.role_id)
        self.phase = PlayerPhaseEnum.SEARCH

    async def _on_talk_turn(self, message: WSMessage) -> None:
        """轮到本角色时公开发言，data["role_id"] 为轮到的角色，data["instruction"] 为可选的发言要求"""
        if self._require(message, "role_id") != self.role_id:
            return
        self._check_phase(PlayerPhaseEnum.DISCUSS)
        content = await self.discussion.speak(message.data.get("instruction", ""))
        self.phase = PlayerPhaseEnum.DISCUSS
        await self.channel.broadcast(
            self._message(MessageType.AGENT_TALK, {"content": content}, message.request_id), exclude=self.role_id
        )

    async def _on_speech(self, message: WSMessage) -> None:
        """他人的公开发言与投票已由发送方写入公共记忆，轮到本角色行动时从记忆中读取"""
        self.logger.log(f"[{self.name}] 收到{message.data.get('from')}的{message.type}")

    async def _on_private_start(self, message: WSMessage) -> None:
        """私聊环节开始，判断是否主动发起私聊"""
        self._check_phase(PlayerPhaseEnum.PRIVATE_CHAT)
        self._sent_private.clear()
        self.phase = PlayerPhaseEnum.PRIVATE_CHAT
        decision = await self.private_chat.decide(self._others())
        if not decision.should_chat or decision.target is None:
            self.logger.log(f"[{self.name}] 不发起私聊：{decision.purpose}")
            return
        content = await self.private_chat.initiate(decision.target, decision.purpose)
        await self._send_private(decision.target, content, create_uuid(MessageType.AGENT_PRIVATE))

    async def _on_private_message(self, message: WSMessage) -> None:
        """
        回复发给本角色的私聊，消息已由发送方写入双方记忆。
        PRIVATE_TALK 来自人类玩家，总是回复；AGENT_PRIVATE 来自 AI 玩家，回复条数受 max_private_replies 限制。
        """
        sender = self._require(message, "from")
        if self._require(message, "to") != self.role_id or sender == self.role_id:
            return
        if self.phase != PlayerPhaseEnum.PRIVATE_CHAT:
            self.logger.warning(f"[{self.name}] 不在私聊环节，忽略{sender}的私聊")
            return
        from_agent = MessageType(message.type) == MessageType.AGENT_PRIVATE
        if from_agent and self._sent_private.get(sender, 0) >= self.max_private_replies:
            self.logger.log(f"[{self.name}] 本章与{sender}的私聊已达上限，不再回复")
            return
        # 双方同时向对方发起私聊时，可能已经回复过对方更新的消息
        last = self.private_chat.memory.get_conversation(sender, limit=1)
        if last and last[0].source == self.role_id:
            return
        content = await self.private_chat.reply(sender)
        await self._send_private(sender, content, message.request_id)

    async def _on_private_end(self, message: WSMessage) -> None:
        """私聊环节结束"""
        self._check_phase(PlayerPhaseEnum.PRIVATE_DONE)
        self.private_chat.end_chat()
        self.phase = PlayerPhaseEnum.PRIVATE_DONE

    async def _on_identify_start(self, message: WSMessage) -> None:
        """最终章指认凶手，data["candidates"] 为可选的候选角色，默认为通道中的其他玩家"""
        if not self.is_final_chapter:
            raise GameError(f"[{self.name}] 只有最终章才能指认凶手，当前为第{self.chapter}章")
        self._check_phase(PlayerPhaseEnum.ACCUSED)
        candidates = message.data.get("candidates") or self._others()
        self.result = await self.accusation.accuse(candidates)
        self.phase = PlayerPhaseEnum.ACCUSED
        data = {"murderer": self.result.murderer, "content": self.result.reason}
        await self.channel.broadcast(self._message(MessageType.AGENT_IDENTIFY, data, message.request_id), exclude=self.role_id)

    # ---------------- 内部方法 ----------------

    def _check_phase(self, target: PlayerPhaseEnum) -> None:
        """校验能否进入目标环节；环节在本环节的行动成功后才更新，失败时主持方可以重发"""
        if self.phase not in _ALLOWED_FROM[target]:
            raise GameError(f"[{self.name}] 当前处于{self.phase.value}环节，不能进入{target.value}环节")

    def _others(self) -> List[str]:
        """通道中的其他玩家"""
        return [role for role in self.channel.roles() if role != self.role_id]

    def _message(self, message_type: MessageType, data: Dict[str, Any], request_id: str | None = None) -> WSMessage:
        """构造本角色发出的消息"""
        return WSMessage(
            type=message_type,
            data={"from": self.role_id, **data},
            character_id=self.character_id,
            request_id=request_id or create_uuid(message_type),
        )

    async def _send_private(self, partner: str, content: str, request_id: str | None) -> None:
        """经消息通道把私聊发给对方，并计入本章的私聊条数"""
        message = self._message(MessageType.AGENT_PRIVATE, {"to": partner, "content": content}, request_id)
        await self.channel.send(partner, message)
        self._sent_private[partner] = self._sent_private.get(partner, 0) + 1

    @staticmethod
    def _require(message: WSMessage, key: str) -> Any:
        value = message.data.get(key)
        if value is None or value == "":
            raise GameError(f"{message.type} 消息缺少 {key}")
        return value

    def _load_identity(self) -> None:
        """注册角色并写入身份信息，已写入过时跳过（如从文件恢复记忆后重新启动）"""
        self.memory_manager.register_role(self.game_id, self.role_id)
        identity = self.discussion.memory.get_memory(filters={"category": MemoryCategoryEnum.IDENTITY})
        if not identity:
            self.memory_manager.load_character(self.game_id, self.character, self.role_id)

    def _load_story(self, chapter: int) -> Story | None:
        """读取本角色某一章的剧本"""
        with get_session() as session:
            stories = StoryRepository(session).get_by_character_id(self.character_id)
        return next((s for s in stories if s.chapter == chapter), None)

    def _load_evidences(self) -> Tuple[List[Evidence], List[Character]]:
        """读取本章的证据与剧本的全部角色，角色用于分配非公开证据"""
        with get_session() as session:
            repository = ScriptRepository(session)
            return repository.get_evidences_by_chapter(self.script_id, self.chapter), repository.get_characters(self.script_id)
