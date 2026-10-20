"""
数据表定义（企业版）
====================
用"类"定义数据库表——SQLAlchemy 会根据这些类自动建表。

四张表：
  users            用户（登录/角色）
  documents        知识库文档记录（文件名、字数）
  document_chunks  知识块（正文 + 向量 embedding）
  approval_records 审批记录（审计用：谁批的、何时批的、结果）
"""

from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, JSON, String, Text

from app.config import EMBEDDING_DIM
from app.db import Base


class User(Base):
    """用户表：登录 + 角色权限"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)   # 只存哈希，不存明文
    role = Column(String(20), nullable=False, default="employee")  # admin / employee
    avatar = Column(String(255), nullable=False, default="👤")  # 头像：emoji 或图片路径(/static/avatars/xx.png)
    created_at = Column(DateTime, default=datetime.utcnow)


class DocumentRecord(Base):
    """文档记录表：知识库里有哪些文件"""
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    chars = Column(Integer, default=0)          # 字数
    chunk_count = Column(Integer, default=0)    # 切分出的知识块数
    created_at = Column(DateTime, default=datetime.utcnow)


class DocumentChunk(Base):
    """知识块表：正文 + 向量（pgvector 列）"""
    __tablename__ = "document_chunks"

    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, index=True)   # 属于哪篇文档
    content = Column(Text, nullable=False)      # 正文
    embedding = Column(Vector(EMBEDDING_DIM))   # ★ 向量列（维度=embedding 模型）


class ApprovalRecord(Base):
    """审批记录表：审计（企业合规必备）"""
    __tablename__ = "approval_records"

    id = Column(Integer, primary_key=True)
    thread_id = Column(String(100), index=True)   # 哪次会话
    tool = Column(String(100))                    # 要执行什么操作
    args_json = Column(Text)                      # 操作参数（JSON 字符串）
    status = Column(String(20))                   # pending / approved / rejected
    decided_by = Column(String(50), nullable=True)  # 谁审批的
    created_at = Column(DateTime, default=datetime.utcnow)
    decided_at = Column(DateTime, nullable=True)


class ChatMessage(Base):
    """对话消息表（普通问答的多轮记忆，企业版：持久化到 PostgreSQL）"""
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True)
    session_id = Column(String(100), index=True)   # 哪次会话
    role = Column(String(20), nullable=False)      # user / ai
    content = Column(Text, nullable=False)
    sources = Column(JSON, nullable=False, default=list)
    created_at = Column(DateTime, default=datetime.utcnow)


class LeaveRequest(Base):
    """请假业务记录；申请人姓名留快照，用户删除后仍能保留审批审计。"""
    __tablename__ = "leave_requests"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    applicant = Column(String(50), nullable=False)
    leave_type = Column(String(20), nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    days = Column(Integer, nullable=False)
    reason = Column(Text, nullable=False)
    status = Column(String(20), nullable=False, default="pending", index=True)
    review_comment = Column(String(500), nullable=False, default="")
    reviewed_by = Column(String(50), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
