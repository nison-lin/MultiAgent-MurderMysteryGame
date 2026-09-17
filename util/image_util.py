"""图片存储工具"""

import asyncio
import os
import uuid
from functools import lru_cache
from typing import List, Optional

from db.image_storage_type import ImageStorageType
from error.errors import ConfigError, OSSError, StorageError
from client.oss_client import OSSClientWrapper

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

@lru_cache(maxsize=1)
def _get_oss_client() -> OSSClientWrapper:
    """返回进程内缓存的OSS客户端。
    """
    return OSSClientWrapper()

def reset_oss_client() -> None:
    """清除缓存的OSS客户端，下次调用时按当前环境变量重建。供测试与配置热更新使用"""
    _get_oss_client.cache_clear()

def _build_filename(filename: Optional[str], index: int, total: int) -> str:
    base = filename or uuid.uuid4().hex
    if total > 1:
        base = f"{base}_{index}"
    return f"{base}.png"

def save_local(
        images: List[bytes], 
        filename: Optional[str] = None, 
        directory: Optional[str] = None,
        base_dir: Optional[str] = None
    ) -> List[str]:
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
    final = os.path.abspath(localDir)
    if not final.startswith(os.path.abspath(baseDir) + os.sep):
        raise ConfigError("非法的图片路径")

    os.makedirs(localDir, exist_ok=True)

    paths: List[str] = []
    for i, image in enumerate(images):
        path = os.path.join(localDir, _build_filename(filename, i, len(images)))
        try:
            # O_EXCL 由操作系统保证"不存在才创建"的原子性，无先查后写的竞态
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        except FileExistsError as e:
            _cleanup_local(paths)
            raise StorageError(f"文件已存在，拒绝覆盖: {path}") from e
        except OSError as e:
            _cleanup_local(paths)
            raise StorageError(f"创建图片文件失败: {path}，原因: {e}") from e
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(image)
        except OSError as e:
            paths.append(path)  # 已创建，需一并清理
            _cleanup_local(paths)
            raise StorageError(f"写入图片文件失败: {path}，原因: {e}") from e
        paths.append(path)
    return paths

def _cleanup_local(paths: List[str]) -> None:
    """回滚本次已写入的本地文件，尽力而为，不掩盖原始异常"""
    for path in paths:
        try:
            os.remove(path)
        except OSError:
            pass

async def save_oss(images: List[bytes], filename: Optional[str] = None, directory: Optional[str] = None) -> List[str]:
    """
    将图片并发上传到阿里云OSS，返回URL列表（顺序与images一致）。
    filename为文件名（不含扩展名），未传入时用uuid生成；多张图片时会自动加序号区分。
    directory为OSS对象key前缀，未传入时为"minimax"。
    """
    if not images:
        raise OSSError("上传文件为空")
    ossClient = _get_oss_client()
    ossDir = (directory or "minimax").rstrip("/")

    objectKeys = [f"{ossDir}/{_build_filename(filename, i, len(images))}" for i in range(len(images))]
    results = await asyncio.gather(
        *[ossClient.upload(image, key, forbid_overwrite=True) for image, key in zip(images, objectKeys)],
        return_exceptions=True
    )

    firstError = next((r for r in results if isinstance(r, BaseException)), None)
    if firstError is None:
        return [str(url) for url in results]

    # 有失败：回滚已成功的部分
    uploaded = [key for key, result in zip(objectKeys, results) if not isinstance(result, BaseException)]
    if uploaded:
        cleanups = await asyncio.gather(
            *[ossClient.delete(key) for key in uploaded], return_exceptions=True
        )
        orphans = [key for key, c in zip(uploaded, cleanups) if isinstance(c, BaseException)]
        if orphans:
            raise OSSError(
                f"上传图片到OSS失败: {firstError}；回滚时以下文件删除失败，需人工清理: {orphans}"
            ) from firstError
    raise OSSError(f"上传图片到OSS失败: {firstError}") from firstError

def update_local(path: str, image: bytes) -> str:
    """
    覆盖写本地图片文件，返回该路径。
    先写临时文件再原子替换，写入中途失败不会损坏原文件。
    """
    directory = os.path.dirname(os.path.abspath(path))
    if not os.path.isdir(directory):
        raise StorageError(f"目标目录不存在: {directory}")

    tempPath = f"{path}.{uuid.uuid4().hex}.tmp"
    try:
        with open(tempPath, "wb") as f:
            f.write(image)
        os.replace(tempPath, path)
    except OSError as e:
        try:
            os.remove(tempPath)
        except OSError:
            pass
        raise StorageError(f"更新图片文件失败: {path}，原因: {e}") from e
    return path

async def update_oss(object_key: str, image: bytes) -> str:
    """
    覆盖写OSS上的指定对象，返回其URL。
    """
    ossClient = _get_oss_client()
    return await ossClient.upload(image, object_key)

def delete_local(path: str) -> None:
    """
    删除本地图片文件。
    """
    if not os.path.exists(path):
        raise StorageError("文件不存在")
    os.remove(path)

async def delete_oss(object_key: str) -> None:
    """
    删除阿里云OSS上的图片文件。
    """
    ossClient = _get_oss_client()
    await ossClient.delete(object_key)

async def save(
        images: List[bytes], 
        filename: Optional[str] = None, 
        directory: Optional[str] = None, 
        storage_type: Optional[ImageStorageType] = None
    ) -> tuple[List[str], ImageStorageType]:
    """
    保存图片，优先使用本地存储：若配置了LOCAL_IMAGE_DIR则存本地，
    否则若配置了阿里云OSS则上传OSS，
    否则存到项目根目录下的image文件夹。
    """
    if storage_type:
        if storage_type == ImageStorageType.LOCAL:
            return save_local(images, filename, directory), ImageStorageType.LOCAL
        if storage_type == ImageStorageType.OSS:
            return await save_oss(images, filename, directory), ImageStorageType.OSS
        else:
            raise StorageError(f"未知的storage_type: {storage_type}，必须是'local'或'oss'。")
        
    if os.getenv("LOCAL_IMAGE_DIR", ""):
        return save_local(images, filename, directory), ImageStorageType.LOCAL

    if all([os.getenv("OSS_ACCESS_KEY_ID"), os.getenv("OSS_ACCESS_KEY_SECRET"),
            os.getenv("OSS_ENDPOINT"), os.getenv("OSS_BUCKET_NAME")]):
        return await save_oss(images, filename, directory), ImageStorageType.OSS

    return save_local(images, filename, directory, base_dir=PROJECT_ROOT), ImageStorageType.LOCAL

async def update(location: str, image: bytes, storage_type: ImageStorageType) -> str:
    """
    覆盖写指定位置的图片，返回其路径或URL。
    storage_type指定存储方式，决定调用update_local还是update_oss。
    location为update_local的path参数或update_oss的object_key参数，
    通常直接取数据库中已存的image_path。
    """
    if storage_type == ImageStorageType.LOCAL:
        return update_local(location, image)
    if storage_type == ImageStorageType.OSS:
        return await update_oss(location, image)
    raise StorageError(f"未知的storage_type: {storage_type}，必须是'local'或'oss'。")

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
        raise StorageError(f"未知的storage_type: {storage_type}，必须是'local'或'oss'。")
