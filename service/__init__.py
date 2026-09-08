"""业务服务模块"""

from .image_service import save_local, save_oss, delete_local, delete_oss, save, delete

__all__ = [
    "save_local",
    "save_oss",
    "delete_local",
    "delete_oss",
    "save",
    "delete",
]
