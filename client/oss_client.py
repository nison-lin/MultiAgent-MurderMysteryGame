"""阿里云OSS客户端"""

import os
import asyncio
import oss2
from dotenv import load_dotenv
from typing import Optional

from error.errors import ConfigError, OSSError

load_dotenv()

class OSSClientWrapper:
    """阿里云OSS客户端封装类"""

    def __init__(self, accessKeyId: Optional[str] = None, accessKeySecret: Optional[str] = None,
                 endpoint: Optional[str] = None, bucketName: Optional[str] = None,
                 customDomain: Optional[str] = None):
        """
        初始化客户端。优先使用传入参数，如果未提供，则从环境变量加载。
        """
        accessKeyId = accessKeyId or os.getenv("OSS_ACCESS_KEY_ID", "")
        accessKeySecret = accessKeySecret or os.getenv("OSS_ACCESS_KEY_SECRET", "")
        endpoint = endpoint or os.getenv("OSS_ENDPOINT", "")
        bucketName = bucketName or os.getenv("OSS_BUCKET_NAME", "")
        self.customDomain = customDomain or os.getenv("OSS_CUSTOM_DOMAIN", "")
        if not all([accessKeyId, accessKeySecret, endpoint, bucketName]):
            raise ConfigError("阿里云OSS的AccessKey、Endpoint和Bucket名称必须被提供或在.env文件中定义。")

        auth = oss2.Auth(accessKeyId, accessKeySecret)
        self.bucket = oss2.Bucket(auth, endpoint, bucketName)
        self.bucketName = bucketName
        self.endpoint = endpoint

    async def upload(self, data: bytes, object_key: str) -> str:
        """
        上传二进制数据到OSS，返回可访问的URL。
        """
        try:
            await asyncio.to_thread(self.bucket.put_object, object_key, data)
        except Exception as e:
            raise OSSError(f"上传文件到OSS时发生错误: {e}")

        if self.customDomain:
            return f"{self.customDomain.rstrip('/')}/{object_key}"
        scheme, _, host = self.endpoint.partition("://")
        if not host:
            host = scheme
            scheme = "https"
        return f"{scheme}://{self.bucketName}.{host}/{object_key}"

    async def delete(self, object_key: str) -> None:
        """
        删除OSS上的指定文件。
        """
        try:
            await asyncio.to_thread(self.bucket.delete_object, object_key)
        except Exception as e:
            raise OSSError(f"删除OSS文件时发生错误: {e}")
