"""LLM客户端"""

import os
from openai import AsyncOpenAI
from dotenv import load_dotenv
from typing import AsyncGenerator, List, Dict, Optional

from error.errors import ConfigError, LLMError

load_dotenv()

class LLMClientWrapper:
    """LLM客户端封装类"""

    def __init__(self, model: Optional[str] = None, apiKey: Optional[str] = None, baseUrl: Optional[str] = None, timeout: Optional[int] = None):
        """
        初始化客户端。优先使用传入参数，如果未提供，则从环境变量加载。
        """
        self.model = model or os.getenv("LLM_MODEL_ID", "")
        apiKey = apiKey or os.getenv("LLM_API_KEY", "")
        baseUrl = baseUrl or os.getenv("LLM_BASE_URL", "")
        timeout = timeout or int(os.getenv("LLM_TIMEOUT", 60))
        if not all([self.model, apiKey, baseUrl]):
            raise ConfigError("模型ID、API密钥和服务地址必须被提供或在.env文件中定义。")

        self.client = AsyncOpenAI(api_key=apiKey, base_url=baseUrl, timeout=timeout)

    async def think_without_tools(self, messages: List[Dict[str, str]], temperature: float = 0) -> str:
        """
        非流式调用，直接返回完整响应内容。
        """
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages, # type: ignore
                temperature=temperature,
                stream=False
            )

            if not response.choices:
                raise LLMError(f"模型响应中没有choices。")
            return response.choices[0].message.content

        except Exception as e:
            raise LLMError(f"调用LLM API时发生错误: {e}")

    async def think_stream_without_tools(self, messages: List[Dict[str, str]], temperature: float = 0) -> AsyncGenerator[str, None]:
        """
        流式调用，逐块 yield 增量内容。调用方用 `async for piece in ...` 消费。
        """
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages, # type: ignore
                temperature=temperature,
                stream=True
            )

            async for chunk in response:
                if not chunk.choices:
                    continue
                content = chunk.choices[0].delta.content or ""
                if content:
                    yield content

        except Exception as e:
            raise LLMError(f"调用LLM API时发生错误: {e}")
        
    async def think_with_tools(self, messages: List[Dict[str, str]], temperature: float = 0, tools: list[dict] | None = None):
        if tools is None:
            tools = []

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages, # type: ignore
                temperature=temperature,
                stream=False,
                tools=tools, # type: ignore
                tool_choice="auto"
            )

            result = response.choices[0].message
            if result.tool_calls or result.content:
                return result
            raise LLMError(f"模型响应中既没有内容也没有工具调用。")

        except Exception as e:
            raise LLMError(f"调用LLM API时发生错误: {e}")