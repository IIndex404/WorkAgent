"""
接口层测试：健康检查 + 参数校验
（不调真实 LLM，只测路由和校验逻辑）
"""

from fastapi.testclient import TestClient


def test_health(client: TestClient):
    """健康检查接口应返回 ok"""
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_chat_validation_empty_message(client: TestClient):
    """空消息应返回 422（Pydantic 校验拦截）"""
    resp = client.post("/chat", json={"message": "", "session_id": "t1"})
    assert resp.status_code == 422


def test_chat_validation_missing_field(client: TestClient):
    """缺字段应返回 422"""
    resp = client.post("/chat", json={})
    assert resp.status_code == 422


def test_approve_requires_admin_token(client: TestClient):
    """审批接口必须先登录（没有令牌 = 401）

    注意这里的顺序问题（面试常问）：
      请求体是空的（本该校验出 422），但返回的是 401。
      因为 FastAPI 先解析依赖（require_admin 要求令牌），依赖没过就直接拦下，
      根本走不到请求体校验。
      → 这正好证明"权限检查在参数校验之前生效"，是安全上正确的顺序：
        不该让未登录的人知道参数格式对不对。
    """
    resp = client.post("/chat/agent/approve", json={})
    assert resp.status_code == 401


def test_approve_rejects_invalid_token(client: TestClient):
    """伪造/过期的令牌也应被拒（401），不能靠前端自觉

    ⚠️ 小坑记录：这里千万别写中文假令牌。
       HTTP 请求头只允许 ASCII（latin-1），塞中文会在发请求前就抛
       UnicodeEncodeError（连服务端都到不了）。用英文字符串伪造即可。
    """
    resp = client.post(
        "/chat/agent/approve",
        json={"thread_id": "t1", "approve": True},
        headers={"Authorization": "Bearer not-a-real-token"},
    )
    assert resp.status_code == 401


def test_admin_endpoints_require_auth(client: TestClient):
    """管理员接口未登录一律 401（真正的权限校验在后端，前端隐藏按钮不算数）"""
    assert client.get("/admin/documents").status_code == 401
    assert client.get("/admin/approvals").status_code == 401
    assert client.get("/auth/users").status_code == 401


def test_register_validation(client: TestClient):
    """注册：用户名过短应被 Pydantic 拦下（422），不需要数据库"""
    resp = client.post("/auth/register", json={"username": "a", "password": "123"})
    assert resp.status_code == 422
