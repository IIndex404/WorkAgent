"""
测试夹具（conftest）
====================
pytest 会自动加载本文件。
这里准备一些所有测试共用的东西，如测试客户端。
"""

import sys
from pathlib import Path

# 确保能 import app 包（以项目根目录为准）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture
def client():
    """提供 FastAPI 测试客户端（用于测接口层，不发真实请求）"""
    from app.main import app

    with TestClient(app) as c:
        yield c
