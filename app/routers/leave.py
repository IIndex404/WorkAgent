"""员工提交与查阅请假、管理员审批；所有身份均来自登录令牌。"""
import json
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_admin
from app.db import get_db
from app.models import ApprovalRecord, LeaveRequest, User
from app.schemas.leave import LeaveCreate, LeaveInfo, LeaveReview

router = APIRouter(tags=["请假申请与审批"])


@router.post("/leave/requests", response_model=LeaveInfo, status_code=201)
def create_leave(req: LeaveCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # 同一用户的提交串行化，防止并发重复/重叠申请。
    db.execute(select(User.id).where(User.id == user.id).with_for_update()).one()
    overlap = db.execute(select(LeaveRequest.id).where(
        LeaveRequest.user_id == user.id,
        LeaveRequest.status.in_(["pending", "approved"]),
        LeaveRequest.start_date <= req.end_date,
        LeaveRequest.end_date >= req.start_date,
    ).limit(1)).first()
    if overlap:
        raise HTTPException(409, "该日期已有待审批或已批准的请假，请勿重复提交")
    record = LeaveRequest(
        user_id=user.id, applicant=user.username, leave_type=req.leave_type,
        start_date=req.start_date, end_date=req.end_date,
        days=(req.end_date - req.start_date).days + 1, reason=req.reason,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.get("/leave/requests", response_model=list[LeaveInfo])
def my_leaves(user: User = Depends(get_current_user), db: Session = Depends(get_db),
              limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    return db.execute(select(LeaveRequest).where(LeaveRequest.user_id == user.id)
                      .order_by(LeaveRequest.id.desc()).offset(offset).limit(limit)).scalars().all()


@router.get("/leave/requests/{request_id}", response_model=LeaveInfo)
def leave_detail(request_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    record = db.get(LeaveRequest, request_id)
    if record is None or (record.user_id != user.id and user.role != "admin"):
        raise HTTPException(404, "申请不存在")
    return record


@router.get("/admin/leave-requests", response_model=list[LeaveInfo])
def admin_leaves(_: User = Depends(require_admin), db: Session = Depends(get_db),
                 status: Literal["pending", "approved", "rejected"] | None = None,
                 limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    stmt = select(LeaveRequest)
    if status:
        stmt = stmt.where(LeaveRequest.status == status)
    return db.execute(stmt.order_by(LeaveRequest.id.desc()).offset(offset).limit(limit)).scalars().all()


@router.post("/admin/leave-requests/{request_id}/review", response_model=LeaveInfo)
def review_leave(request_id: int, req: LeaveReview, admin: User = Depends(require_admin),
                 db: Session = Depends(get_db)):
    record = db.execute(select(LeaveRequest).where(LeaveRequest.id == request_id).with_for_update()).scalar_one_or_none()
    if record is None:
        raise HTTPException(404, "申请不存在")
    if record.status != "pending":
        raise HTTPException(409, "该申请已处理，不能重复审批")
    reviewed_at = datetime.utcnow()
    record.status = req.decision
    record.review_comment = req.comment
    record.reviewed_by = admin.username
    record.reviewed_at = reviewed_at
    db.add(ApprovalRecord(
        thread_id=f"leave:{record.id}", tool="leave_request",
        args_json=json.dumps({"request_id": record.id, "applicant": record.applicant,
                              "leave_type": record.leave_type, "start_date": str(record.start_date),
                              "end_date": str(record.end_date), "days": record.days,
                              "comment": req.comment}, ensure_ascii=False),
        status=req.decision, decided_by=admin.username, decided_at=reviewed_at,
    ))
    db.commit()
    db.refresh(record)
    return record
