"""工具基类"""

import functools
import inspect
from typing import Any, Awaitable, Callable, Union

from langchain_core.tools import BaseTool, StructuredTool, ToolException
from langchain_core.tools.base import create_schema_from_function

from error.errors import BaseError

ToolFunc = Callable[..., Union[Any, Awaitable[Any]]]

__all__ = ["BaseTool", "ToolFunc", "create_tool"]


def create_tool(name: str, description: str, func: ToolFunc) -> BaseTool:
    """
    把函数包装为 LangChain 工具，参数的 JSON Schema 由函数签名推断，
    参数说明用 Annotated[类型, "说明"] 标注，可以是同步函数或异步函数。
    函数抛出的业务异常（BaseError、ValueError）转为 ToolException，以错误文本作为工具结果返回给模型，让其自行修正。
    """
    schema = create_schema_from_function(name, func, parse_docstring=False)

    def to_tool_error(e: Exception) -> ToolException:
        return ToolException(f"错误：工具 {name} 执行失败：{e}")

    if inspect.iscoroutinefunction(func):
        @functools.wraps(func)
        async def acall(**kwargs: Any) -> Any:
            try:
                return await func(**kwargs)
            except (BaseError, ValueError) as e:
                raise to_tool_error(e) from e

        return StructuredTool.from_function(
            coroutine=acall, name=name, description=description, args_schema=schema, handle_tool_error=True
        )

    @functools.wraps(func)
    def call(**kwargs: Any) -> Any:
        try:
            return func(**kwargs)
        except (BaseError, ValueError) as e:
            raise to_tool_error(e) from e

    return StructuredTool.from_function(
        func=call, name=name, description=description, args_schema=schema, handle_tool_error=True
    )
