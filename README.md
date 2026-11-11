# Multi-Agent 剧本杀

<div align="center">

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
![Python Version](https://img.shields.io/badge/Python-3.12%2B-blue)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey)
[![nison-lin](https://img.shields.io/badge/GitHub-nison--lin-181717?logo=github)](https://github.com/nison-lin)

</div>

基于大语言模型多 Agent 的「剧本杀」后端服务：一名人类玩家与若干 AI 角色同台推凶，由不扮演任何角色的**主持方（GameHandler）**驱动「读本 → 搜证 → 讨论 → 私聊 → 指认」的完整流程，阶段转移由 LangGraph 状态机管理。项目同时内置一个 **Plan-and-Execute 剧本创作 Agent**，可用一句话生成包含角色、时间线、分章剧本与证据链的完整剧本。

- 实时交互：WebSocket 单连接，消息级 `request_id` 关联请求与回复
- 角色隔离：每个角色独立的私有记忆 + 一局游戏共享的公共记忆，AI 无法读到别人的剧本与私有证据
- 可解释推理：发言、私聊、指认分别由三个子 Agent 完成，各自持有结构化记忆与专用工具
- 数据落库：剧本、角色、剧本分章、证据、背景故事、房间状态全部持久化到 MySQL

---

## 技术栈

| 类别 | 选型 |
| --- | --- |
| 语言 | Python 3.12+ |
| Web 框架 | FastAPI + uvicorn |
| LLM | LangChain Core 1.x + langchain-openai |
| ORM / 数据库 | SQLAlchemy 2.x + PyMySQL + MySQL 8 |
| 数据模型 | Pydantic v2 |
| 图片能力 | MiniMax、阿里云 OSS |

---

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

依赖清单见 [requirements.txt](requirements.txt)，版本为本机实测可用的组合（Python 3.13.9）。两点注意：

- `uvicorn[standard]` 里的 `standard` 不能省，否则缺少 `websockets`，WebSocket 连接无法建立
- `PyMySQL` 是 `mysql+pymysql://` 连接串的驱动，`DATABASE_URL` 改用其他驱动时需相应替换

项目使用 LangChain 1.x 的接口（`ChatOpenAI.bind_tools`、`langchain_core.messages`），不要降级到 0.x。

### 2. 配置环境变量

```bash
cp .env.example .env
```

至少需要填写：

| 变量 | 说明 |
| --- | --- |
| `DATABASE_URL` | `mysql+pymysql://用户名:密码@主机:端口/库名?charset=utf8mb4` |
| `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL_ID` | 大模型服务地址、密钥、模型名 |

其余项见[配置参考](#配置参考)。`.env` 已被 `.gitignore` 忽略，注意不要提交密钥。

### 3. 初始化数据库

只需先在 MySQL 中创建空库（名称与 `DATABASE_URL` 中一致）：

```sql
CREATE DATABASE murder_mystery DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

### 4. 启动服务

```bash
uvicorn core.app:app --host 0.0.0.0 --port 8000 --workers 1
```

启动成功后可访问健康检查：

```bash
curl http://127.0.0.1:8000/health
# {"status":"ok","sessions":0}
```

`sessions` 为当前在线 WebSocket 会话数。交互式 API 文档在 `/docs`（当前仅 `/health` 与 WebSocket 端点）。

---

## 使用方式

### 1. 生成剧本（可选）

`CreateAgent` 会按固定七步生成剧本并写入数据库，全部完成后剧本状态置为「已完成」。目前没有对应的 HTTP 接口，需在代码或脚本中调用：

```python
import asyncio

from agent.create_agent import CreateAgent

async def main() -> None:
    agent = CreateAgent(
        name="剧本创作",
        system_prompt="你是剧本杀创作助手",
        user_input="民国上海，一座洋楼里的家族遗产争夺案，需要 5 人本",
        player_count=5,
        script_type="推理",  # 推理 / 情感 / 恐怖
    )
    script_id = await agent.run()
    print("剧本ID:", script_id)

asyncio.run(main())
```

生成过程中的中间结果全部保留在 Agent 实例上（`backstory`、`truth`、`characters`、`timeline`、`stories`、`evidences`）；任一步失败时已入库的数据保留，剧本仍为「草稿」。也可以跳过本步骤，直接向 `script`、`character`、`story`、`evidence`、`backstory` 表写入自己的剧本数据。

### 2. 开始一局游戏

连接 `ws://127.0.0.1:8000/ws/{session_id}`，收到 `connected` 后发送 `start` 消息，服务端在 `data` 中返回你的角色与全部角色，然后在后台推进整局流程。

```json
{"type": "start", "data": {"script_id": 1}}
```

- `session_id` 由客户端自定义（建议 UUID），同一 `session_id` 同时只能进行一局游戏
- `data.character_id` 可选，指定扮演的角色必须属于该剧本；不填则随机选择一个**非凶手**角色
- 一局游戏只允许一名人类玩家，其余角色全部由 AI 扮演
- 剧本至少需要 2 个角色，且角色名不能重复（角色名即 AI 内部的角色 ID）

---

## 配置参考

全部通过 `.env` 注入（`core/app.py` 是唯一加载点，各模块亦做了 `load_dotenv` 兜底）。

### 数据库

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `DATABASE_URL` | 无（必填） | SQLAlchemy 连接串 |
| `ECHO` | `false` | 是否打印 SQL |
| `POOL_SIZE` | `10` | 连接池大小 |
| `MAX_OVERFLOW` | `20` | 连接池溢出上限 |

### WebSocket

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `WS_HEARTBEAT_INTERVAL` | `30` | 服务端心跳巡检间隔（秒） |
| `WS_HEARTBEAT_TIMEOUT` | `90` | 超过该时长无任何消息即断开，必须大于巡检间隔 |
| `WS_MAX_CONNECTIONS` | `32` | 同时在线会话上限 |
| `WS_MAX_MESSAGE_BYTES` | `65536` | 单条消息字节上限 |
| `WS_SEND_TIMEOUT` | `10` | 单次发送超时（秒），防止慢客户端拖住广播 |

### 游戏流程（单位：秒）

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `GAME_TALK_ROUNDS` | `2` | 每章讨论的发言轮数，必须 > 0 |
| `GAME_AI_TALK_TIMEOUT` | `120` | 等待 AI 发言超时 |
| `GAME_HUMAN_TALK_TIMEOUT` | `180` | 等待人类发言超时 |
| `GAME_PRIVATE_DURATION` | `180` | 每章私聊环节时长 |
| `GAME_AI_IDENTIFY_TIMEOUT` | `180` | 等待 AI 指认超时 |
| `GAME_HUMAN_IDENTIFY_TIMEOUT` | `300` | 等待人类指认超时 |
| `GAME_DISCONNECT_TIMEOUT` | `300` | 人类离线超过该时长结束游戏 |
| `GAME_MAX_PRIVATE_REPLIES` | `3` | AI 每章对同一 AI 的私聊条数上限 |
| `GAME_LOG_DIR` | 项目根目录 `logs/` | 记忆存档目录 |

### LLM

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `LLM_BASE_URL` | `https://api.deepseek.com/v1` | OpenAI 兼容接口地址 |
| `LLM_API_KEY` | 无（必填） | 密钥 |
| `LLM_MODEL_ID` | `deepseek-v4-flash` | 模型名 |
| `LLM_TIMEOUT` | `60` | 请求超时（秒） |

### 图片与存储（可选）

| 变量 | 说明 |
| --- | --- |
| `MINIMAX_API_KEY` / `MINIMAX_GROUP_ID` / `MINIMAX_IMAGE_MODEL` / `MINIMAX_TIMEOUT` | MiniMax 文生图 |
| `LOCAL_IMAGE_DIR` | 本地图片目录，配置后优先于 OSS |
| `OSS_ACCESS_KEY_ID` / `OSS_ACCESS_KEY_SECRET` / `OSS_ENDPOINT` / `OSS_BUCKET_NAME` / `OSS_CUSTOM_DOMAIN` | 阿里云 OSS |

### 其他

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `CORS_ORIGINS` | `http://localhost:3000,http://127.0.0.1:3000` | 逗号分隔的跨域来源，留空则只放行本地 |

---

## 日志与存档

- 运行日志：`logs/log.txt`，格式 `[YYYY-MM-DD HH:MM:SS]  内容`，警告前缀 `WARNING:`
- 记忆存档：每局结束写入 `logs/game_{game_id}_{YYYYMMDDHHMMSS}.json`，包含轮次、全局序号、公共记忆、各角色记忆与各 Agent 的短期记忆；目录由 `GAME_LOG_DIR` 指定
- 存档失败不会影响游戏结束流程，只记录日志

---

## 许可证

本项目基于 [MIT License](LICENSE) 开源。
