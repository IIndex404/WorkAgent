"""
项目配置模块
============
所有配置集中在 .env（复制 .env.example 改名）。
本模块负责读取 WorkAgent 的环境配置，便于独立部署。
"""

import os

from dotenv import load_dotenv

# 读取项目根目录的 .env
load_dotenv()

# LLM 配置
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")

# Embedding 配置
EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "openai")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
EMBEDDING_BASE_URL = os.getenv("EMBEDDING_BASE_URL", "https://api.siliconflow.cn/v1")
EMBEDDING_API_KEY = os.getenv("EMBEDDING_API_KEY", "")

# Rerank 重排序配置（硅基流动，可选；失败会自动降级为原顺序）
RERANK_MODEL = os.getenv("RERANK_MODEL", "BAAI/bge-reranker-v2-m3")
RERANK_BASE_URL = os.getenv("RERANK_BASE_URL", "https://api.siliconflow.cn/v1/rerank")
USE_RERANK = os.getenv("USE_RERANK", "1") == "1"

# 混合检索（向量 + BM25 关键词 → RRF 融合，提升召回率）
USE_HYBRID = os.getenv("USE_HYBRID", "1") == "1"

# LangSmith 可观测性（可选：不配不影响运行，配了能看全链路追踪）
# LangChain 会自动读取这些环境变量并启用追踪
LANGCHAIN_TRACING_V2 = os.getenv("LANGCHAIN_TRACING_V2", "")
LANGCHAIN_API_KEY = os.getenv("LANGCHAIN_API_KEY", "")
LANGCHAIN_PROJECT = os.getenv("LANGCHAIN_PROJECT", "workagent")

# ---- 数据库（企业版：PostgreSQL + pgvector）----
# 对应 docker-compose.yml 里的配置
# 注意：+psycopg 告诉 SQLAlchemy 用 psycopg3 驱动（我们装的是 psycopg[binary]）
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg://ai:ai123456@localhost:5432/ai_assistant")
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "1024"))  # 必须匹配 embedding 模型维度

# ---- 鉴权（企业版：JWT）----
JWT_SECRET = os.getenv("JWT_SECRET", "change-me-in-production")
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "1440"))
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")

# ---- 日志（企业版：loguru）----
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# 知识库文档目录（相对项目根目录）
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

# 需要人工审批的工具名列表
APPROVAL_TOOLS = {"send_official_notice"}
