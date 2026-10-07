"""创建剧本的智能体"""

PLAN_PROMPT = """
你是剧本杀生成系统的 Planner。你的唯一任务是：把用户的描述拆解成一份结构化的任务计划（DAG），不生成任何剧本内容。

## 输入
用户描述：{user_input}
剧本人数：{player_count}
剧本类型：{type}

## 规划原则
1. 必须先确定"核心诡计与真相"，再倒推角色、时间线、证据、剧本。真相是全局锚点。
2. 明确每个任务的依赖关系（dependencies），被依赖的任务必须先完成。
3. 每个任务要写清：产出物、依赖、验收标准。
4. 任务粒度适中：一个任务只产出一类结构化内容。

## 任务模板
- T1 确定标题、简介、预计时长
- T2 世界观与背景故事（依赖：T1）
- T3 核心诡计与真相（依赖：T2）
- T4 角色背景与人物关系（依赖：T2,T3）
- T5 案发时间线（依赖：T3,T4）
- T6 各角色剧本（依赖：T2,T3,T4,T5）
- T7 证据链（依赖：T3,T4,T5,T6）

## 要求
1. 请严格按照任务模板的七步来规划，不要增加或者减少步骤。
2. 最终只输出一个JSON字符串数组，不要输出其他内容，例如：[\"步骤1\", \"步骤2\"]
"""

BASIC_INFO_PROMPT = """
你是剧本杀策划，执行确定剧本标题、简介和预计时长的任务。

## 输入
用户输入：{user_input}
任务要求：{plan}
玩家人数：{player_count}
剧本类型：{type}

## 要求
1. 标题简短有记忆点（4-12字），贴合剧本类型与用户描述，不得直接剧透凶手或诡计。
2. 简介100-200字，交代故事舞台、案件引子和玩家要面对的悬念，以"案件发生、真相待解"收尾，不透露真相。
3. 预计时长为整数小时，需与玩家人数和剧本类型匹配：人数越多、推理越复杂，时长越长，一般在3-6小时之间。
4. 若用户输入中已明确标题、时长等信息，以用户输入为准。

## 输出格式
只输出一个JSON对象，不要输出其他内容：
{{"title": "剧本标题", "description": "剧本简介", "duration_hours": 4}}
"""

BACKSTORY_PROMPT = """
你是剧本杀背景故事创作者，执行创建世界观与背景故事的任务。

## 输入
用户输入：{user_input}
任务要求：{plan}
玩家人数：{player_count}
剧本类型：{type}
剧本标题：{title}
剧本简介：{description}
预计游玩时长：{duration_hours}

## 要求
1. 产出一个具体、可落地的世界观，避免空泛形容词堆砌。
2. 背景要为后续凶案提供合理土壤：存在利益冲突、隐秘关系或封闭环境。
3. 设定需"本格友好"：不使用超自然力量作为核心解释（除非用户要求设计超自然世界观）。
4. 语言凝练，300-500字，包含时代、地点、核心矛盾三要素。
"""

TRUTH_PROMPT = """
你是剧本杀核心诡计设计师，执行设计案件核心诡计与真相的任务。真相是整个剧本的全局锚点，后续角色、时间线、剧本和证据都将据此倒推。

## 输入
用户输入：{user_input}
任务要求：{plan}
玩家人数：{player_count}
剧本类型：{type}
剧本简介：{description}
世界观与背景故事：{backstory}

## 要求
1. 死者为非玩家角色（NPC），凶手为玩家角色之一，且只有一名凶手（除非用户明确要求多凶手或共犯）。
2. 动机必须扎根于背景故事中的核心矛盾，足以驱使一个正常人铤而走险，不能是"天生残忍""一时兴起"之类的空洞理由。
3. 作案手法须在世界观设定下物理上可行，写清作案工具、作案时间、作案地点和具体步骤；不使用超自然力量（除非世界观本身允许）。
4. 诡计（如伪造不在场证明、伪装死亡时间、密室、嫁祸）要有至少一个可被证据拆穿的破绽，玩家能通过逻辑推理唯一锁定凶手，不能依赖巧合或"凶手自己承认"。
5. 设计2-3条误导方向，使其他角色也有合理嫌疑，但每条误导都必须能被证据排除。
6. 只描述人物在故事中的身份定位（如"死者的商业合伙人"），不要为角色起名，具体角色由后续任务创建，但需保证玩家人数为{player_count}人时每个角色都有可分配的嫌疑点。
7. 剧本类型要求：推理本侧重手法严密、线索闭环；情感本让动机承载情感冲突与人物羁绊；恐怖本在真相中保留可解释的恐怖氛围来源。

## 输出格式
按以下小标题分段输出，不要输出其他内容：
【死者】身份及与背景故事的关联
【凶手】身份定位及动机
【作案过程】时间、地点、工具、步骤
【核心诡计】诡计内容及破绽
【误导方向】每条误导及其排除方式
【推理路径】玩家从关键证据推出凶手的逻辑链
"""

CHARACTER_PROMPT = """
你是剧本杀角色设计师，执行创建角色背景与人物关系的任务。

## 输入
用户输入：{user_input}
任务要求：{plan}
玩家人数：{player_count}
剧本类型：{type}
剧本简介：{description}
世界观与背景故事：{backstory}
核心诡计与真相：{truth}

## 要求
1. 恰好创建{player_count}个玩家角色，不包含死者；其中只有一人is_murderer为true，且必须与真相中的凶手身份定位一致。
2. 每个角色都与死者有直接关联，且至少与另外一名角色存在关系（亲属、恋人、同事、仇人、债务等），人物关系网要互相交织而非各自孤立。
3. 每个角色都要有一个不愿公开的秘密和一个看似合理的作案动机，使所有人都有嫌疑；非凶手角色的秘密要能解释其可疑行为，但不能构成杀人事实。
4. 角色之间性格、立场、目标要有区分度，避免同质化，保证每位玩家都有可玩的内容。
5. background只写该角色的公开身份、经历和人物关系，不写秘密和真相；秘密写在secret字段，供后续任务使用。
6. background应尽量简洁明了，最多不能超过250字。
7. gender只能取"男"、"女"、"非人类"、"未知"之一；age为整数。

## 输出格式
只输出一个JSON数组，不要输出其他内容：
[{{"name": "角色名", "gender": "男", "age": 30, "profession": "职业", "background": "公开背景与人物关系", "secret": "角色秘密与动机", "is_murderer": false}}]
"""

TIMELINE_PROMPT = """
你是剧本杀时间线设计师，执行梳理案发时间线的任务。

## 输入
用户输入：{user_input}
任务要求：{plan}
玩家人数：{player_count}
剧本类型：{type}
世界观与背景故事：{backstory}
核心诡计与真相：{truth}
角色背景与人物关系：{characters}

## 要求
1. 覆盖从案发前的关键起因到尸体被发现的完整过程，时间精确到分钟级别，按时间先后排序。
2. 每个角色在案发前后的关键时段都要有明确的行踪，不留无法解释的空白；同一时刻一个角色只能出现在一个地点。
3. 凶手的作案过程要完整落在时间线中，作案所需的移动、准备、清理时间必须合理，与地点之间的距离相符。
4. 凶手伪造的不在场证明与真实行踪要分别标注，并且要有至少一处与其他角色的所见或物证相矛盾，作为可被拆穿的破绽。
5. 非凶手角色的可疑行为（如秘密会面、偷拿物品）也要体现在时间线中，并能自圆其说。
6. 标注每个事件有哪些角色知情或目击，后续每个角色的剧本只能包含其知情的事件。
7. 必须与核心诡计与真相完全一致，不得新增与之矛盾的情节。

## 输出格式
只输出一个JSON数组，不要输出其他内容：
[{{"time": "21:30", "location": "地点", "characters": ["在场角色"], "event": "事件描述", "witnesses": ["知情或目击角色"], "is_fake": false}}]
其中is_fake为true表示该事件是凶手伪造的、对外宣称的经过。
"""

STORY_PROMPT = """
你是剧本杀角色剧本作家，执行为每个角色撰写个人剧本的任务。

## 输入
用户输入：{user_input}
任务要求：{plan}
玩家人数：{player_count}
剧本类型：{type}
预计游玩时长：{duration_hours}
世界观与背景故事：{backstory}
核心诡计与真相：{truth}
角色背景与人物关系：{characters}
案发时间线：{timeline}

## 要求
1. 为全部{player_count}个角色各写一份剧本，所有角色的章节数相同，章节数根据预计时长确定（一般2-4章），chapter从1开始连续编号，最后一章is_end为true，其余为false。
2. 以第二人称"你"书写，只包含该角色亲身经历、目击或知情的内容，严格遵守时间线中的witnesses信息，不能出现该角色不可能知道的信息。
3. 第一章交代角色身世、与其他角色的关系、秘密和案发当天的行踪；后续章节随游戏推进释放新的回忆、任务和关键信息，推动玩家搜证与交流。
4. 凶手的剧本要写明真实作案经过，并给出隐瞒建议和可用的说辞；非凶手的剧本要给出其需要隐瞒的秘密以及个人任务，让其有理由回避某些问题。
5. 各角色剧本中对同一事件的描述必须相互吻合，仅视角和知情程度不同；涉及的时间、地点、物品须与时间线一致。
6. 结尾章节（is_end为true）在投票后阅读，揭示该角色的结局与心路历程，需与真相呼应。
7. 剧本类型要求：推理本信息密度高、细节可推敲；情感本注重人物内心与情感爆发点；恐怖本营造氛围和心理压迫感。
8. 每章600-1500字，语言风格与世界观相符。

## 输出格式
只输出一个JSON数组，不要输出其他内容：
[{{"character_name": "角色名", "stories": [{{"chapter": 1, "content": "章节内容", "is_end": false}}]}}]
"""

EVIDENCE_PROMPT = """
你是剧本杀证据设计师，执行设计证据链的任务。

## 输入
用户输入：{user_input}
任务要求：{plan}
玩家人数：{player_count}
核心诡计与真相：{truth}
角色背景与人物关系：{characters}
案发时间线：{timeline}
各角色剧本：{stories}

## 要求
1. 证据必须能支撑真相中的推理路径：综合关键证据可以唯一锁定凶手，并拆穿其核心诡计和伪造的不在场证明。
2. 每个角色至少有1-2条指向其秘密或嫌疑的证据，制造嫌疑分散；所有误导性证据都要能被其他证据或剧本内容合理解释。
3. 证据内容要具体（如物品描述、书信原文、监控记录、尸检报告），与时间线和各角色剧本中的细节完全一致，不得凭空引入新事实。
4. 证据按章节分配，chapter与角色剧本的章节对应（结尾章节除外），关键证据不宜集中在第一章，形成逐步逼近真相的节奏。
5. is_public为true表示所有玩家可见（如尸检报告、现场勘查），false表示需搜证获得；公开证据数量应少于搜证证据。
6. 证据总数与玩家人数相匹配，一般为玩家人数的4-6倍。
7. 证据必须简洁明了，避免冗长的叙述或复杂的推理过程，确保玩家能够在游戏中快速理解和使用，最多不能超过150字。

## 输出格式
只输出一个JSON数组，不要输出其他内容：
[{{"name": "证据名称", "content": "证据内容", "chapter": 1, "is_public": false}}]
"""

import json
from typing import Any, List, NamedTuple, Optional

from client.llm_client import LLMClientWrapper
from agent.plan_agent import PlanAgent
from agent.tool.base_tool import BaseTool
from db.database import get_session
from db.entity.script_entity import ScriptStatusEnum
from db.repository import CharacterRepository, ScriptRepository
from error.errors import DataError, LLMError, UserInputError
from model.backstory import Backstory
from model.character import Character
from model.evidence import Evidence
from model.script import Script
from model.story import Story

# 计划步骤数与模型输出不符时使用的默认步骤，顺序与各步骤提示词一一对应
DEFAULT_STEPS = [
    "确定标题、简介、预计时长",
    "世界观与背景故事",
    "核心诡计与真相",
    "角色背景与人物关系",
    "案发时间线",
    "各角色剧本",
    "完成证据链",
]


class StepConfig(NamedTuple):
    """单个创作步骤的配置"""
    prompt: str      # 步骤提示词模板
    key: str         # 结果存放的属性名，需要存储时对应 _save_{key} 方法
    is_json: bool    # 模型输出是否为JSON
    need_save: bool  # 是否需要存入数据库


# 顺序与 DEFAULT_STEPS 一一对应
STEP_CONFIGS = [
    StepConfig(BASIC_INFO_PROMPT, "basic_info", True, True),   # 解析后展开为 title/description/duration_hours
    StepConfig(BACKSTORY_PROMPT, "backstory", False, True),
    StepConfig(TRUTH_PROMPT, "truth", False, False),
    StepConfig(CHARACTER_PROMPT, "characters", True, True),
    StepConfig(TIMELINE_PROMPT, "timeline", True, False),
    StepConfig(STORY_PROMPT, "stories", True, True),
    StepConfig(EVIDENCE_PROMPT, "evidences", True, True),
]

class CreateAgent(PlanAgent):
    """创建剧本的智能体

    继承自 PlanAgent，使用计划-执行的流程来创建剧本。
    """

    user_input: str
    player_count: int
    script_type: str

    steps: List[str] | None = None
    title: str | None = None
    description: str | None = None
    duration_hours: int | None = None
    backstory: str | None = None
    truth: str | None = None
    characters: List[dict] | None = None
    timeline: List[dict] | None = None
    stories: List[dict] | None = None
    evidences: List[dict] | None = None
    script_id: int | None = None

    # JSON解析失败时的最大重试次数
    MAX_PARSE_RETRIES = 2

    def __init__(
        self,
        name: str,
        system_prompt: str,
        llm: Optional[LLMClientWrapper] = None,
        tools: Optional[List[BaseTool]] = None,
        max_steps: int = 5,
        temperature: float = 0.7,
        max_plan_steps: int = 8,
        user_input: str = "",
        player_count: int = 4,
        script_type: str = "推理",
    ):
        super().__init__(name, system_prompt, llm, tools, max_steps, temperature, max_plan_steps)
        if not user_input:
            raise UserInputError("user_input不能为空")
        self.user_input = user_input
        self.player_count = player_count
        self.script_type = script_type

    async def run(self) -> int:
        """
        规划 -> 依次执行各创作步骤，每步结果按 STEP_CONFIGS 存入数据库，全部完成后将剧本标记为已完成。
        中途失败时已完成步骤的数据保留在库中，剧本保持草稿状态。
        :return: 剧本ID
        """
        await self.plan()
        steps = self.steps or list(DEFAULT_STEPS)
        for i, (step, config) in enumerate(zip(steps, STEP_CONFIGS), 1):
            prompt = config.prompt.format(**self._prompt_vars(step))
            await self.execute(prompt, config)
            self.logger.log(f"[{self.name}] 创作步骤 {i}/{len(STEP_CONFIGS)} 完成：{config.key}")

        script_id = self._require_script_id()
        with get_session() as session:
            ScriptRepository(session).update(Script(id=script_id, status=ScriptStatusEnum.ARCHIVED))
        self.logger.log(f"[{self.name}] 剧本 {script_id} 创作完成")
        return script_id

    def _prompt_vars(self, step: str) -> dict[str, Any]:
        """构造步骤提示词的格式化变量，JSON结果转为文本；各提示词只取自己用到的变量"""
        def dump(value: Any) -> Any:
            return json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value

        return {
            "user_input": self.user_input,
            "plan": step,
            "player_count": self.player_count,
            "type": self.script_type,
            "title": self.title,
            "description": self.description,
            "duration_hours": self.duration_hours,
            "backstory": self.backstory,
            "truth": self.truth,
            "characters": dump(self.characters),
            "timeline": dump(self.timeline),
            "stories": dump(self.stories),
        }

    async def plan(self):
        """
        根据用户描述生成剧本创作计划。
        后续每一步都按下标对应固定的提示词，因此步骤数必须与 DEFAULT_STEPS 一致，否则使用默认步骤。
        """
        prompt = PLAN_PROMPT.format(user_input=self.user_input, player_count=self.player_count, type=self.script_type)
        steps = await super().plan(self.user_input, prompt=prompt)
        if len(steps) != len(DEFAULT_STEPS):
            self.logger.warning(f"[{self.name}] 计划步骤数 {len(steps)} 与预期 {len(DEFAULT_STEPS)} 不符，使用默认步骤")
            steps = list(DEFAULT_STEPS)
        self.steps = steps
    
    async def execute(self, prompt: str, config: StepConfig) -> Any:
        """
        执行单个创作步骤：清空历史后以给定提示词独立运行一次 ReAct 循环。
        JSON步骤会解析输出，解析失败时重试；结果存到 config.key 对应的属性上，
        config.need_save 为 True 时再写入数据库。
        :return: 解析后的结果，文本步骤为字符串，JSON步骤为字典或列表
        """
        result: Any = None
        for attempt in range(1, self.MAX_PARSE_RETRIES + 2):
            self.reset()
            content = await self.react(prompt)
            result = self._parse_result(content, config)
            if result is not None:
                break
            self.logger.warning(f"[{self.name}] 步骤 {config.key} 输出解析失败（第{attempt}次）：{content}")
        if result is None:
            raise LLMError(f"步骤 {config.key} 输出解析失败，已重试{self.MAX_PARSE_RETRIES}次")

        if config.key == "basic_info":
            self.title = result.get("title")
            self.description = result.get("description")
            self.duration_hours = result.get("duration_hours")
        else:
            setattr(self, config.key, result)

        if config.need_save:
            saver = getattr(self, f"_save_{config.key}", None)
            if saver is None:
                raise DataError(f"步骤 {config.key} 需要存储，但未实现 _save_{config.key}")
            saver(result)
            self.logger.log(f"[{self.name}] 步骤 {config.key} 结果已存入数据库")
        return result

    def _parse_result(self, content: str, config: StepConfig) -> Any:
        """解析步骤输出。文本步骤要求非空；basic_info 要求JSON对象，其余JSON步骤要求对象数组。失败返回None"""
        if not config.is_json:
            return content.strip() or None
        data = self._parse_steps(content)
        if config.key == "basic_info":
            return data if isinstance(data, dict) and data else None
        if isinstance(data, list) and data and all(isinstance(item, dict) for item in data):
            return data
        return None

    def _require_script_id(self) -> int:
        """关联数据必须挂在已存储的剧本下"""
        if self.script_id is None:
            raise DataError("剧本尚未存储，请先执行 basic_info 步骤")
        return self.script_id

    def _save_basic_info(self, result: dict) -> None:
        """新建剧本，记录剧本ID供后续步骤关联"""
        script = Script(
            title=result.get("title"),
            description=result.get("description"),
            duration_hours=result.get("duration_hours"),
            player_count=self.player_count,
            script_type=self.script_type,  # type: ignore[arg-type]
        )
        with get_session() as session:
            self.script_id = ScriptRepository(session).save(script).id

    def _save_backstory(self, result: str) -> None:
        """存储背景故事"""
        script_id = self._require_script_id()
        with get_session() as session:
            ScriptRepository(session).update_backstory(script_id, Backstory(content=result))

    def _save_characters(self, result: List[dict]) -> None:
        """存储角色。secret 等模型中没有的字段会被忽略，仅保留在内存中供后续步骤使用"""
        script_id = self._require_script_id()
        for item in result:
            if not all(k in item for k in ("name", "gender", "age", "profession", "background", "secret", "is_murderer")):
                self.logger.warning(f"[{self.name}] 角色缺少必要字段，跳过：{item}")
                continue
            if len(item.get("background", "")) > 255:
                self.logger.warning(f"[{self.name}] 角色背景过长（>255字），跳过：{item}")
                continue
        characters = [Character.model_validate(item) for item in result]
        with get_session() as session:
            ScriptRepository(session).update_characters(script_id, characters)

    def _save_stories(self, result: List[dict]) -> None:
        """按角色名找到已存储的角色，存储其各章节剧本"""
        script_id = self._require_script_id()
        with get_session() as session:
            character_repository = CharacterRepository(session)
            name_to_id = {c.name: c.id for c in character_repository.get_by_script_id(script_id)}
            for item in result:
                character_id = name_to_id.get(item.get("character_name"))
                if character_id is None:
                    self.logger.warning(f"[{self.name}] 剧本中的角色 {item.get('character_name')} 不存在，跳过")
                    continue
                stories = [Story.model_validate(story) for story in item.get("stories", [])]
                character_repository.update_stories(character_id, stories)

    def _save_evidences(self, result: List[dict]) -> None:
        """存储证据链"""
        script_id = self._require_script_id()
        for item in result:
            if not all(k in item for k in ("name", "content", "chapter", "is_public")):
                self.logger.warning(f"[{self.name}] 证据缺少必要字段，跳过：{item}")
                continue
            if len(item.get("content", "")) > 255:
                self.logger.warning(f"[{self.name}] 证据内容过长（>255字），跳过：{item}")
                continue
        evidences = [Evidence.model_validate(item) for item in result]
        with get_session() as session:
            ScriptRepository(session).update_evidences(script_id, evidences)
