"""工具基类"""

from dataclasses import dataclass, field
import inspect
from typing import Any, Awaitable, Callable, Dict, Union

ToolFunc = Callable[..., Union[Any, Awaitable[Any]]]

@dataclass
class BaseTool:
    """
    Agent可调用的工具。
    parameters 为 JSON Schema 格式的参数定义，func 可以是同步函数或异步函数。
    """
    name: str
    description: str
    func: ToolFunc
    parameters: Dict[str, Any] = field(default_factory=lambda: {"type": "object", "properties": {}})

    def to_schema(self) -> Dict[str, Any]:
        """转换为 OpenAI function calling 的工具描述格式"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    async def invoke(self, **kwargs) -> Any:
        """执行工具，兼容同步与异步函数"""
        result = self.func(**kwargs)
        if inspect.isawaitable(result):
            result = await result
        return result
