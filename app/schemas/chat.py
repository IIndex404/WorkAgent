"""
接口数据模型
============
定义 API 的请求/响应格式（契约）。
好处：参数校验自动完成（FastAPI 用 Pydantic 校验），前后端格式有据可依。
"""

from pydantic import BaseModel, Field


# ---------- 请求模型 ----------
class ChatRequest(BaseModel):
    """普通问答请求"""
    message: str = Field(..., min_length=1, max_length=2000, description="用户消息")
    session_id: str = Field("default", max_length=100, description="会话编号（记忆用）")


class AgentRequest(BaseModel):
    """智能体问答请求"""
    message: str = Field(..., min_length=1, max_length=2000, description="用户消息")
    session_id: str = Field("default", max_length=100, description="会话编号（记忆用）")


class ApproveRequest(BaseModel):
    """人工审批请求"""
    thread_id: str = Field(..., description="待审批的会话编号")
    approve: bool = Field(..., description="true=同意，false=拒绝")


# ---------- 响应模型 ----------
class SourceInfo(BaseModel):
    citation: int
    document_id: int
    document_name: str
    chunk_id: int
    content: str


class ChatResponse(BaseModel):
    """普通问答响应"""
    reply: str
    session_id: str
    sources: list[SourceInfo] = Field(default_factory=list)


class AgentResponse(BaseModel):
    """智能体响应：要么直接回答，要么等待审批"""
    status: str = Field(..., description="done=已完成 / awaiting_approval=等待审批")
    reply: str = Field("", description="AI 的回答（status=done 时有）")
    session_id: str = ""
    approval: dict | None = Field(None, description="审批信息（status=awaiting_approval 时有）")


class DocumentInfo(BaseModel):
    """知识库文档信息"""
    id: int
    name: str
    chunk_count: int
    characters: int
    created_at: str = ""


# ---------- 用户（注册 / 管理）----------
class RegisterRequest(BaseModel):
    """用户注册请求（公开接口，默认注册为 employee）"""
    username: str = Field(..., min_length=2, max_length=50, description="用户名（至少2位）")
    password: str = Field(..., min_length=3, max_length=64, description="密码（至少3位）")


class UserInfo(BaseModel):
    """用户信息（管理员查看）"""
    id: int
    username: str
    role: str
    created_at: str = ""


class RoleUpdateRequest(BaseModel):
    """修改用户角色请求（管理员）"""
    role: str = Field(..., description="admin 或 employee")


class AvatarUpdateRequest(BaseModel):
    """修改头像请求（用户自己）"""
    avatar: str = Field(..., min_length=1, max_length=20, description="头像（emoji）")


# ---------- 审批记录（管理员查看）----------
class ApprovalInfo(BaseModel):
    """审批记录（审计）"""
    id: int
    thread_id: str
    tool: str
    args_json: str
    status: str
    decided_by: str | None = None
    created_at: str = ""
    decided_at: str | None = None
