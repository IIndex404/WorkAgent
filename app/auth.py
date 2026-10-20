"""
鉴权模块（企业版：JWT）
=======================
流程（大白话）：
  1. 用户登录（用户名+密码）→ 验证密码 → 发一个"令牌"（JWT）
  2. 之后每次请求带上令牌 → 服务器解令牌 → 知道"你是谁、什么角色"
  3. 管理员接口检查角色 → 不是 admin 就 403 拒绝

概念：
  哈希    = 密码只存"加密后的样子"，数据库泄露也拿不到明文
  JWT     = 一段带签名的令牌（含用户信息+过期时间），无法伪造
"""

from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.config import JWT_EXPIRE_MINUTES, JWT_SECRET
from app.db import get_db
from app.models import User

# 声明"登录接口在 /auth/login"（Swagger 会用它做"Authorize"按钮）
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def hash_password(password: str) -> str:
    """明文密码 → 哈希（存库用这个）。
    直接用 bcrypt（不用 passlib：新版 bcrypt 与 passlib 有兼容问题）"""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    """校验：用户输入的密码 和 库里存的哈希 对不对得上"""
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


def create_access_token(user: User) -> str:
    """生成 JWT 令牌（含用户身份 + 过期时间）"""
    payload = {
        "sub": user.username,        # 令牌里装用户名
        "role": user.role,           # 令牌里装角色
        "exp": datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """从请求的令牌里解出用户（每个需要登录的接口都靠它）"""
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="登录已失效，请重新登录",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        username = payload.get("sub")
        if username is None:
            raise credentials_exc
    except JWTError:
        raise credentials_exc

    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise credentials_exc
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    """角色校验：只有 admin 能过（管理员接口用它）"""
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user
