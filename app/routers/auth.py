"""
认证接口（企业版：注册 + 登录 + 用户管理）
==========================================
公开接口：
  POST /auth/register   注册（默认角色 employee）
  POST /auth/login      登录 → JWT 令牌
  GET  /auth/me         查看当前用户

管理员接口（require_admin）：
  GET    /auth/users               用户列表
  DELETE /auth/users/{user_id}     删除用户
  PATCH  /auth/users/{user_id}/role 修改角色（提升/降级）

Swagger 使用：先 /auth/login 拿 access_token → Authorize 粘贴 → 之后自动带上。
"""

import os
import time

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.auth import (
    create_access_token,
    get_current_user,
    hash_password,
    require_admin,
    verify_password,
)
from app.db import get_db
from app.models import User
from app.schemas.chat import AvatarUpdateRequest, RegisterRequest, RoleUpdateRequest, UserInfo

router = APIRouter(prefix="/auth", tags=["认证"])


@router.post("/register")
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    """注册（公开）：新用户默认角色 employee"""
    exists = db.query(User).filter(User.username == req.username).first()
    if exists:
        raise HTTPException(status_code=400, detail="用户名已存在")
    user = User(username=req.username, password_hash=hash_password(req.password), role="employee")
    db.add(user)
    db.commit()
    return {"status": "ok", "message": f"注册成功：{req.username}（角色：employee）"}


@router.post("/login")
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """登录：用户名+密码 → 返回令牌（Swagger 的 Authorize 用这个）"""
    user = db.query(User).filter(User.username == form.username).first()
    if not user or not verify_password(form.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")

    token = create_access_token(user)
    return {
        "access_token": token,
        "token_type": "bearer",
        "role": user.role,
        "username": user.username,
        "avatar": user.avatar or "👤",
    }


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    """查看当前登录用户（个人信息弹窗用）"""
    return {
        "username": user.username,
        "role": user.role,
        "avatar": user.avatar or "👤",
        "created_at": str(user.created_at)[:19] if user.created_at else "",
    }


@router.patch("/me/avatar")
def update_avatar(req: AvatarUpdateRequest, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    """修改自己的头像（emoji 方式）"""
    user.avatar = req.avatar
    db.commit()
    return {"status": "ok", "avatar": user.avatar}


# 头像上传目录（app/static/avatars，已随 /static 挂载对外可访问）
_AVATAR_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "avatars")
_ALLOWED_AVATAR_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
_MAX_AVATAR_SIZE = 2 * 1024 * 1024  # 2MB


@router.post("/me/avatar/upload")
def upload_avatar(file: UploadFile, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    """上传照片当头像（员工和管理员都可以）"""
    ext = "." + (file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else "")
    if ext not in _ALLOWED_AVATAR_EXT:
        raise HTTPException(status_code=400, detail=f"仅支持 {_ALLOWED_AVATAR_EXT} 格式")

    content = file.file.read()
    if len(content) > _MAX_AVATAR_SIZE:
        raise HTTPException(status_code=400, detail="图片不能超过 2MB")

    os.makedirs(_AVATAR_DIR, exist_ok=True)
    filename = f"u{user.id}_{int(time.time())}{ext}"
    with open(os.path.join(_AVATAR_DIR, filename), "wb") as f:
        f.write(content)

    user.avatar = f"/static/avatars/{filename}"   # 存访问路径（前端直接 <img> 用）
    db.commit()
    return {"status": "ok", "avatar": user.avatar}


# ================= 管理员：用户管理 =================
@router.get("/users", response_model=list[UserInfo])
def list_users(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    """用户列表（管理员）"""
    users = db.query(User).order_by(User.id).all()
    return [
        UserInfo(
            id=u.id, username=u.username, role=u.role,
            created_at=str(u.created_at)[:19] if u.created_at else "",
        )
        for u in users
    ]


@router.delete("/users/{user_id}")
def delete_user(user_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """删除用户（管理员；不能删自己）"""
    if admin.id == user_id:
        raise HTTPException(status_code=400, detail="不能删除自己")
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    db.delete(user)
    db.commit()
    return {"status": "ok", "message": f"已删除用户：{user.username}"}


@router.patch("/users/{user_id}/role")
def update_user_role(user_id: int, req: RoleUpdateRequest,
                     admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """修改用户角色（管理员：提升/降级）"""
    if req.role not in ("admin", "employee"):
        raise HTTPException(status_code=400, detail="角色只能是 admin 或 employee")
    if admin.id == user_id:
        raise HTTPException(status_code=400, detail="不能修改自己的角色")
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    user.role = req.role
    db.commit()
    return {"status": "ok", "message": f"用户 {user.username} 角色已改为 {req.role}"}
