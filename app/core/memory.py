"""
记忆存储（企业版：PostgreSQL 检查点）
====================================
把 LangGraph 的"游戏存档"从内存搬进 PostgreSQL：
  - 服务重启，记忆不丢（之前 InMemorySaver 一重启就清零）
  - 多台服务器共享同一份记忆（横向扩容前提）
  - 生产标准做法（LangGraph 官方支持）

注意：连接是"懒加载"的——第一次真正用到图时才连数据库，
这样数据库没启动时，服务也能启动（/health 正常）。
"""

from psycopg import Connection

from langgraph.checkpoint.postgres import PostgresSaver

from app.config import DATABASE_URL

_checkpointer: PostgresSaver | None = None


def get_checkpointer() -> PostgresSaver:
    """获取检查点保存器（懒加载单例）"""
    global _checkpointer
    if _checkpointer is None:
        # psycopg3 连接（prepare_threshold=0 是 PostgresSaver 的要求）
        # ⚠️ psycopg 不认识 SQLAlchemy 的 "+psycopg" 后缀，连之前要去掉
        psycopg_url = DATABASE_URL.replace("postgresql+psycopg://", "postgresql://")
        conn = Connection.connect(psycopg_url, autocommit=True, prepare_threshold=0)
        _checkpointer = PostgresSaver(conn)
        _checkpointer.setup()  # 自动建检查点表
    return _checkpointer


def get_session_config(session_id: str) -> dict:
    """根据会话编号生成图运行配置（thread_id 相同=同一份记忆）"""
    return {"configurable": {"thread_id": session_id}}
