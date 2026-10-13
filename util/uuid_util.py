"""uuid工具类"""

import uuid

def create_uuid(rex: str|None = None):
    u = str(uuid.uuid4())
    if rex:
        u = rex + "." + u
    return u