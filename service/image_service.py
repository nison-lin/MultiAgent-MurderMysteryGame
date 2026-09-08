"""图片存储服务"""

import os
import uuid
from typing import List, Optional

from ..db.image_storage_type import ImageStorageType
from error.errors import ConfigError
from client.oss_client import OSSClientWrapper

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def _build_filename(filename: Optional[str], index: int, total: int) -> str:
    base = filename or uuid.uuid4().hex
    if total > 1:
        base = f"{base}_{index}"
    return f"{base}.png"

def save_local(images: List[bytes], filename: Optional[str] = None, directory: Optional[str] = None,
               base_dir: Optional[str] = None) -> List[str]:
    """
    将图片保存到本地LOCAL_IMAGE_DIR下，返回本地路径列表。
    filename为文件名（不含扩展名），未传入时用uuid生成；多张图片时会自动加序号区分。
    directory为LOCAL_IMAGE_DIR/image下的子目录。路径不存在会自动创建。
    base_dir覆盖LOCAL_IMAGE_DIR，供未配置任何存储时的默认兜底使用。
    """
    baseDir = base_dir or os.getenv("LOCAL_IMAGE_DIR", "")
    if not baseDir:
        raise ConfigError("本地图片存储必须在.env文件中配置LOCAL_IMAGE_DIR。")

    localDir = os.path.join(baseDir, "image")
    if directory:
        localDir = os.path.join(localDir, directory)
    os.makedirs(localDir, exist_ok=True)

    paths = []
    for i, image in enumerate(images):
        path = os.path.join(localDir, _build_filename(filename, i, len(images)))
        with open(path, "wb") as f:
            f.write(image)
        paths.append(path)
    return paths

async def save_oss(images: List[bytes], filename: Optional[str] = None, directory: Optional[str] = None) -> List[str]:
    """
    将图片上传到阿里云OSS，返回URL列表。
    filename为文件名（不含扩展名），未传入时用uuid生成；多张图片时会自动加序号区分。
    directory为OSS对象key前缀，未传入时为"minimax"。
    """
    ossClient = OSSClientWrapper()
    ossDir = (directory or "minimax").rstrip("/")

    urls = []
    for i, image in enumerate(images):
        objectKey = f"{ossDir}/{_build_filename(filename, i, len(images))}"
        url = await ossClient.upload(image, objectKey)
        urls.append(url)
    return urls

def delete_local(path: str) -> None:
    """
    删除本地图片文件。
    """
    os.remove(path)

async def delete_oss(object_key: str) -> None:
    """
    删除阿里云OSS上的图片文件。
    """
    ossClient = OSSClientWrapper()
    await ossClient.delete(object_key)

async def save(images: List[bytes], filename: Optional[str] = None, directory: Optional[str] = None) -> tuple[List[str], ImageStorageType]:
    """
    保存图片，优先使用本地存储：若配置了LOCAL_IMAGE_DIR则存本地，
    否则若配置了阿里云OSS则上传OSS，
    否则存到项目根目录下的image文件夹。
    """
    if os.getenv("LOCAL_IMAGE_DIR", ""):
        return save_local(images, filename, directory), ImageStorageType.LOCAL

    if all([os.getenv("OSS_ACCESS_KEY_ID"), os.getenv("OSS_ACCESS_KEY_SECRET"),
            os.getenv("OSS_ENDPOINT"), os.getenv("OSS_BUCKET_NAME")]):
        return await save_oss(images, filename, directory), ImageStorageType.OSS

    return save_local(images, filename, directory, base_dir=PROJECT_ROOT), ImageStorageType.LOCAL

async def delete(location: str, storage_type: ImageStorageType) -> None:
    """
    删除图片，storage_type指定存储方式："local"或"oss"，决定调用delete_local还是delete_oss。
    location为delete_local的path参数或delete_oss的object_key参数。
    """
    if storage_type == ImageStorageType.LOCAL:
        delete_local(location)
    elif storage_type == ImageStorageType.OSS:
        await delete_oss(location)
    else:
        raise ValueError(f"未知的storage_type: {storage_type}，必须是'local'或'oss'。")
