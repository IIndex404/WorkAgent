"""
应用入口（企业版）
==================
启动：uvicorn app.main:app --reload --port 8000
文档：http://127.0.0.1:8000/docs

启动时自动做：
  1. 连接 PostgreSQL，创建所有表（users/documents/document_chunks/approval_records）
  2. 创建初始管理员账号（admin/admin123，可在 .env 改）
  3. 重建知识库索引（文档 → 切分 → 向量 → 入库）
  4. 打印 LangSmith / Rerank 状态

设计：数据库不可用时，服务照常启动（/health 正常），功能接口再报错——
"启动失败不致命"，保证可观测性接口永远活着。
"""

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.auth import hash_password
from app.config import (
    ADMIN_PASSWORD,
    ADMIN_USERNAME,
    LANGCHAIN_API_KEY,
    LANGCHAIN_PROJECT,
    LANGCHAIN_TRACING_V2,
    USE_RERANK,
)
from app.core.logger import logger
from app.db import SessionLocal, init_db
from app.models import User
from app.routers import admin, auth, chat, leave
from app.services.document_service import rebuild_index

app = FastAPI(
    title="WorkAgent | 企业内部业务智能体 API",
    description="企业制度与事务助手：可核对资料出处的RAG问答、员工请假申请、管理员审批与结果查询、工具调用和流式输出",
    version="3.1.0",
)

# 跨域（前端开发时需要）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(auth.router)   # /auth/login 等（登录）
app.include_router(chat.router)   # /chat 等（问答/流式/智能体/审批）
app.include_router(admin.router)  # /admin 等（知识库管理，需管理员）
app.include_router(leave.router)

# ---- 前端页面（Vue 3，前后端分离：前端只管展示，后端只管 API）----
# 用户端：  http://127.0.0.1:8000/        （index.html）
# 管理端：  http://127.0.0.1:8000/admin    （admin.html）
_STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")  # app/static/


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(os.path.join(_STATIC_DIR, "index.html"))


@app.get("/admin", include_in_schema=False)
def admin_page():
    return FileResponse(os.path.join(_STATIC_DIR, "admin.html"))


app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")


@app.get("/health")
def health():
    """健康检查（不依赖数据库，永远可用）"""
    return {"status": "ok"}


def _seed_admin() -> None:
    """创建初始管理员（不存在才创建）"""
    with SessionLocal() as db:
        exists = db.query(User).filter(User.username == ADMIN_USERNAME).first()
        if not exists:
            db.add(User(
                username=ADMIN_USERNAME,
                password_hash=hash_password(ADMIN_PASSWORD),
                role="admin",
            ))
            db.commit()
            logger.info(f"✅ 已创建管理员账号：{ADMIN_USERNAME}")
        else:
            logger.info(f"管理员账号已存在：{ADMIN_USERNAME}")


@app.on_event("startup")
def on_startup():
    """开机自启：建表 → 管理员 → 知识库（每一步失败都不阻断启动）"""
    # 1. 数据库建表
    try:
        init_db()
        logger.info("✅ 数据库连接成功，表已就绪")
    except Exception as e:
        logger.error(f"❌ 数据库不可用（请先 docker compose up -d）：{e}")

    # 2. 初始管理员
    try:
        _seed_admin()
    except Exception as e:
        logger.error(f"⚠️ 管理员初始化失败：{e}")

    # 3. 知识库索引
    try:
        info = rebuild_index()
        logger.info(f"✅ 知识库就绪：{info['documents']} 个文档，{info['chunks']} 个知识块")
    except Exception as e:
        logger.warning(f"⚠️ 知识库初始化跳过（可在 /admin/documents 上传后重建）：{e}")

    # 4. 可观测性状态
    if LANGCHAIN_TRACING_V2 == "true" and LANGCHAIN_API_KEY:
        logger.info(f"✅ LangSmith 追踪已启用（项目：{LANGCHAIN_PROJECT}）")
    else:
        logger.info("ℹ️  LangSmith 未配置（可选）")
    logger.info(f"ℹ️  Rerank 精排：{'启用（失败自动降级）' if USE_RERANK else '关闭'}")
    logger.info("🚀 服务就绪：http://127.0.0.1:8000/docs")
