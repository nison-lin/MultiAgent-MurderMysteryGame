"""MiniMax图片生成客户端"""

import os
import base64
import httpx
from dotenv import load_dotenv
from typing import List, Optional

from error.errors import BaseError, ConfigError, MiniMaxError

load_dotenv()

class MiniMaxClientWrapper:
    """MiniMax图片生成客户端封装类"""

    def __init__(self, apiKey: Optional[str] = None, groupId: Optional[str] = None,
                 model: Optional[str] = None, timeout: Optional[int] = None):
        """
        初始化客户端。优先使用传入参数，如果未提供，则从环境变量加载。
        """
        apiKey = apiKey or os.getenv("MINIMAX_API_KEY", "")
        groupId = groupId or os.getenv("MINIMAX_GROUP_ID", "")
        self.model = model or os.getenv("MINIMAX_IMAGE_MODEL", "image-01")
        self.timeout = timeout or int(os.getenv("MINIMAX_TIMEOUT", 60))
        if not all([apiKey, groupId]):
            raise ConfigError("MiniMax API密钥和GroupId必须被提供或在.env文件中定义。")

        self.url = f"https://api.minimax.chat/v1/image_generation?GroupId={groupId}"
        self.headers = {
            "Authorization": f"Bearer {apiKey}",
            "Content-Type": "application/json",
        }

    async def generate_image(self, prompt: str, aspect_ratio: str = "1:1", n: int = 1) -> List[bytes]:
        """
        调用MiniMax图片生成接口，返回解码后的图片二进制数据列表。
        """
        payload = {
            "model": self.model,
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "response_format": "base64",
            "n": n,
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(self.url, headers=self.headers, json=payload)
                response.raise_for_status()
                data = response.json()

            if data.get("base_resp", {}).get("status_code") != 0:
                raise MiniMaxError(f"MiniMax返回错误: {data.get('base_resp', {}).get('status_msg')}")

            result = [base64.b64decode(b64) for b64 in data.get("data", {}).get("image_base64") or []]
            if not result:
                raise MiniMaxError("MiniMax没有返回图片")

        except BaseError:
            raise
        except Exception as e:
            raise MiniMaxError(f"调用MiniMax图片生成API时发生错误: {e}")
