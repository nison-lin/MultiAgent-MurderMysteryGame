from enum import Enum


class ImageStorageType(str, Enum):
    LOCAL = "local"
    OSS = "oss"