"""LLM客户端"""

import os
from typing import AsyncGenerator, Optional, Sequence

from dotenv import load_dotenv
from langchain_core.language_models import LanguageModelInput
from langchain_core.messages import AIMessage
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI

from error.errors import BaseError, ConfigError, LLMError

load_dotenv()

class LLMClientWrapper:
    """LLM客户端封装类，底层为 LangChain 的 ChatOpenAI，消息使用 LangChain 的消息类型"""

    def __init__(self, model: Optional[str] = None, apiKey: Optional[str] = None, baseUrl: Optional[str] = None, timeout: Optional[int] = None):
        """
        初始化客户端。优先使用传入参数，如果未提供，则从环境变量加载。
        """
        try:
            self.model = model or os.getenv("LLM_MODEL_ID", "")
            apiKey = apiKey or os.getenv("LLM_API_KEY", "")
            baseUrl = baseUrl or os.getenv("LLM_BASE_URL", "")
            try:
                timeout = timeout or int(os.getenv("LLM_TIMEOUT", 60))
            except ValueError as e:
                raise ConfigError(f"模型的timeout必须是整数")
            if not all([self.model, apiKey, baseUrl]):
                raise ConfigError("模型ID、API密钥和服务地址必须被提供或在.env文件中定义。")

        except BaseError:
            raise
        except Exception as e:
            raise ConfigError(f"模型配置出错：{e}")

        # 供 LangGraph 等需要直接使用 ChatModel 的场景
        self.chat_model = ChatOpenAI(model=self.model, api_key=apiKey, base_url=baseUrl, timeout=timeout)  # type: ignore[arg-type]

    async def think_without_tools(self, messages: LanguageModelInput, temperature: float = 0) -> str:
        """
        非流式调用，直接返回完整响应内容。
        """
        try:
            response = await self.chat_model.bind(temperature=temperature).ainvoke(messages)
        except Exception as e:
            raise LLMError(f"调用LLM API时发生错误: {e}")

        content = response.text
        if not content:
            raise LLMError("模型响应内容为空。")
        return content

    async def think_stream_without_tools(self, messages: LanguageModelInput, temperature: float = 0) -> AsyncGenerator[str, None]:
        """
        流式调用，逐块 yield 增量内容。调用方用 `async for piece in ...` 消费。
        """
        try:
            async for chunk in self.chat_model.bind(temperature=temperature).astream(messages):
                if chunk.text:
                    yield chunk.text
        except Exception as e:
            raise LLMError(f"调用LLM API时发生错误: {e}")

    async def think_with_tools(self, messages: LanguageModelInput, temperature: float = 0, tools: Sequence[BaseTool] | None = None) -> AIMessage:
        """
        带工具的调用，返回模型消息：tool_calls 为解析好的工具调用，invalid_tool_calls 为参数不是合法JSON的调用。
        """
        try:
            model = self.chat_model.bind_tools(list(tools), tool_choice="auto") if tools else self.chat_model
            response = await model.bind(temperature=temperature).ainvoke(messages)
        except Exception as e:
            raise LLMError(f"调用LLM API时发生错误: {e}")

        if not isinstance(response, AIMessage):
            raise LLMError(f"模型响应类型错误：{type(response).__name__}")
        if response.tool_calls or response.invalid_tool_calls or response.text:
            return response
        raise LLMError(f"模型响应中既没有内容也没有工具调用。")
