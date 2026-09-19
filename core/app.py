"""应用入口：装配FastAPI应用，统一管理启动与关闭"""

import os
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.websocket.ws_config import init_ws_config
from core.websocket.ws_manager import get_ws_manager, init_ws_manager
from core.websocket.ws_router import router as ws_router
from db.database import get_database, init_database
from util.log_util import LogUtil

# 全项目唯一的环境变量加载点
load_dotenv()

_log = LogUtil()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """启动时初始化数据库与连接管理器，关闭时释放资源"""
    init_database()
    config = init_ws_config()
    manager = init_ws_manager(config)
    manager.start_monitor()
    _log.log("应用启动完成")
    try:
        yield
    finally:
        await get_ws_manager().shutdown()
        get_database().dispose()
        _log.log("应用已关闭")


def _origins() -> list[str]:
    """允许的跨域来源，逗号分隔；未配置时只放行本地开发地址"""
    raw = os.getenv("CORS_ORIGINS", "").strip()
    if not raw:
        return ["http://localhost:3000", "http://127.0.0.1:3000"]
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


def create_app() -> FastAPI:
    """创建并配置FastAPI应用"""
    app = FastAPI(title="MultiAgent 剧本杀", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(ws_router)

    @app.get("/health")
    async def health() -> dict[str, object]:
        """健康检查，返回当前在线会话数"""
        return {"status": "ok", "sessions": await get_ws_manager().count()}

    return app


app = create_app()
