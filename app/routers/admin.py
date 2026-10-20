"""
管理接口（企业版）：知识库管理 + 审批审计（需管理员登录）
========================================================
文档管理：
  GET    /admin/documents              文档列表（分页）
  POST   /admin/documents              上传文档
  DELETE /admin/documents/{doc_id}     删除文档（删库 + 删文件）

审批审计：
  GET    /admin/approvals              审批记录列表（谁批的/何时/结果）
"""

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile

from app.auth import require_admin
from app.models import ApprovalRecord, User
from app.schemas.chat import ApprovalInfo, DocumentInfo
from app.services import document_service

router = APIRouter(prefix="/admin", tags=["知识库管理"])

# 允许的文档格式
_ALLOWED_EXTENSIONS = {".txt"}


# ================= 文档管理 =================
@router.get("/documents", response_model=list[DocumentInfo])
def list_documents(
    _: User = Depends(require_admin),
    limit: int = Query(50, ge=1, le=200, description="每页条数"),
    offset: int = Query(0, ge=0, description="偏移量"),
):
    """查看知识库文档列表（管理员，支持分页）"""
    docs = document_service.list_documents(limit=limit, offset=offset)
    return [
        DocumentInfo(
            id=d["id"], name=d["name"], chunk_count=d["chunks"],
            characters=d["characters"], created_at=d["created_at"],
        )
        for d in docs
    ]


@router.post("/documents")
def upload_document(file: UploadFile, _: User = Depends(require_admin)):
    """上传文档到知识库并重建索引（管理员）"""
    ext = "." + file.filename.rsplit(".", 1)[-1].lower()
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"仅支持 {_ALLOWED_EXTENSIONS} 格式")

    content = file.file.read().decode("utf-8", errors="ignore")
    document_service.add_document_file(file.filename, content)

    return {"status": "ok", "message": f"文档 {file.filename} 已入库并重建索引"}


@router.delete("/documents/{doc_id}")
def delete_document(doc_id: int, _: User = Depends(require_admin)):
    """删除文档（管理员）：删数据库记录 + 知识块 + 物理文件 + 重建索引"""
    try:
        name = document_service.delete_document(doc_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"status": "ok", "message": f"文档 {name} 已删除"}


# ================= 审批审计 =================
@router.get("/approvals", response_model=list[ApprovalInfo])
def list_approvals(
    _: User = Depends(require_admin),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """审批记录列表（管理员，审计用）"""
    from app.db import SessionLocal

    with SessionLocal() as db:
        records = (
            db.query(ApprovalRecord)
            .order_by(ApprovalRecord.id.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
    return [
        ApprovalInfo(
            id=r.id, thread_id=r.thread_id, tool=r.tool, args_json=r.args_json,
            status=r.status, decided_by=r.decided_by,
            created_at=str(r.created_at)[:19] if r.created_at else "",
            decided_at=str(r.decided_at)[:19] if r.decided_at else None,
        )
        for r in records
    ]
