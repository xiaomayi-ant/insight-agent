from __future__ import annotations

import logging
from typing import List

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.core.settings import load_settings
from src.core.logging_config import setup_logging_from_settings
from .routers.v1 import router as v1_router

# 加载配置并设置日志
_settings = load_settings()
setup_logging_from_settings(_settings)


def _parse_cors_origins() -> List[str]:
    """解析CORS origins配置，从settings读取"""
    settings = load_settings()
    raw = settings.cors_origins
    if not raw or not raw.strip():
        # 默认允许本地开发环境
        return ["http://localhost:3000", "http://127.0.0.1:3000"]
    return [x.strip() for x in raw.split(",") if x.strip()]


def create_app() -> FastAPI:
    app = FastAPI(title="ttes", version="0.1.0")

    origins = _parse_cors_origins()
    # 始终添加CORS中间件，即使没有配置origins也允许本地开发
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(v1_router, prefix="/v1")
    return app


app = create_app()


