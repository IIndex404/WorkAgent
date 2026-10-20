"""
文档服务测试（企业版）
======================
注意：企业版文档入库依赖 PostgreSQL（pgvector），
没有数据库时这些测试默认跳过（pytest -m "not db" 跳过 db 标记）。
运行需要数据库：docker compose up -d 之后，去掉 skip 标记再跑。
"""

import pytest

from app.services.document_service import _load_documents

pytestmark = pytest.mark.skipif(
    True, reason="企业版需要 PostgreSQL（先 docker compose up -d，再取消本行跳过）"
)


def test_load_documents_from_data_dir():
    """data 目录下应有员工手册文档"""
    docs = _load_documents()
    assert len(docs) >= 1
    assert "考勤" in docs[0].page_content or "员工手册" in docs[0].page_content


def test_split_produces_multiple_chunks():
    """切分应该产生多个小块"""
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    docs = _load_documents()
    splitter = RecursiveCharacterTextSplitter(chunk_size=100, chunk_overlap=20)
    chunks = splitter.split_documents(docs)
    assert len(chunks) > 1


def test_rebuild_index_with_db():
    """向量化入库 PostgreSQL（需要数据库 + embedding 密钥）"""
    from app.services.document_service import rebuild_index

    info = rebuild_index()
    assert info["chunks"] > 0
