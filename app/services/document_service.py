"""
文档服务（企业版）：知识库的"进货 + 建档 + 检索 + 删除"
=====================================================
职责：
  1. 加载 data 目录的文档（.txt，可扩展 PDF/Word）
  2. 文本切分（chunk）
  3. 向量化 → 存入 PostgreSQL（pgvector 向量列）
  4. 混合检索：向量检索 + BM25 关键词 → RRF 融合（提升召回率）
  5. 增删改查：重建索引 / 添加 / 删除文档（管理员）

教学版 → 企业版的变化：
  - InMemoryVectorStore（内存） → document_chunks 表（PostgreSQL 落盘）
  - 无关键词检索 → BM25（rank_bm25 + jieba 中文分词）
  - 无删除功能 → delete_document（删库 + 删文件）
"""

import json
import os

from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sqlalchemy import delete, select, text

from app.config import DATA_DIR, USE_HYBRID
from app.core.llm import get_embeddings
from app.db import SessionLocal
from app.models import DocumentChunk, DocumentRecord

# BM25 关键词检索（可选依赖：装不上就自动降级为纯向量检索）
try:
    import jieba
    from rank_bm25 import BM25Okapi

    _BM25_AVAILABLE = True
except ImportError:
    _BM25_AVAILABLE = False

_chunk_size = 200
_chunk_overlap = 50

# 内存 BM25 索引（rebuild_index / delete 时重建；不重新向量化）
_bm25: BM25Okapi | None = None
_bm25_chunks: list[str] = []


# ============ 混合检索核心（可单测的纯函数） ============
def rrf_fuse(vector_texts: list[str], bm25_texts: list[str], k: int = 3) -> list[str]:
    """RRF（Reciprocal Rank Fusion）融合：把两路排名的结果合并重排。
    原理：每个文档得分 = Σ 1/(60 + 排名)。两路都排前面的文档得分最高。
    面试讲点：混合检索 = 向量（语义）+ 关键词（精确）互补，RRF 融合两路排名。"""
    fused: dict[str, float] = {}
    for rank, text in enumerate(vector_texts):
        fused[text] = fused.get(text, 0.0) + 1.0 / (60 + rank + 1)
    for rank, text in enumerate(bm25_texts):
        fused[text] = fused.get(text, 0.0) + 1.0 / (60 + rank + 1)
    ranked = sorted(fused, key=fused.get, reverse=True)
    return ranked[:k]


# ============ 加载 / 建索引 ============
def _load_documents() -> list:
    """加载 data 目录下所有 .txt 文件为 Document 列表"""
    docs = []
    if not os.path.isdir(DATA_DIR):
        return docs
    for filename in os.listdir(DATA_DIR):
        if not filename.endswith(".txt"):
            continue
        path = os.path.join(DATA_DIR, filename)
        docs.extend(TextLoader(path, encoding="utf-8").load())
    return docs


def _rebuild_bm25(texts: list[str]) -> None:
    """重建内存 BM25 索引（不重新向量化，只更新关键词索引）"""
    global _bm25, _bm25_chunks
    _bm25_chunks = list(texts)
    if _BM25_AVAILABLE and texts:
        _bm25 = BM25Okapi([list(jieba.cut(t)) for t in texts])
    else:
        _bm25 = None


def _split_by_document(docs: list) -> list[tuple[str, int, list]]:
    """按"来源文档"切分，返回 [(文件名, 字数, 该文档自己的知识块列表), ...]

    为什么单独抽成一个函数：
      它是**纯函数**——不连数据库、不调 embedding API，所以可以脱离环境直接单测。
      （原来的切分逻辑埋在 rebuild_index 里，必须起数据库才能测，结果 bug 一直没被发现）

    ★ 这里修掉过一个真 bug：
      旧写法是 `chunks = splitter.split_documents(docs)` 先把所有文档切成一个大列表，
      然后"给每篇文档都挂上这一整份 chunks"——导致知识块被放大 N 倍（N=文档数）：
        2 篇文档、共 16 块 → 数据库里实际写入 32 行，且每篇文档都声称自己有 16 块。
      正确做法：**每篇文档只挂自己切出来的块**。
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=_chunk_size, chunk_overlap=_chunk_overlap
    )
    groups: list[tuple[str, int, list]] = []
    for doc in docs:
        name = os.path.basename(doc.metadata.get("source", "unknown"))
        chunks = splitter.split_documents([doc])   # 只切这一篇
        groups.append((name, len(doc.page_content), chunks))
    return groups


def rebuild_index() -> dict:
    """重建知识库索引：加载 -> 按文档切分 -> 向量化 -> 存入 PostgreSQL + 重建 BM25"""
    docs = _load_documents()
    if not docs:
        raise FileNotFoundError(f"data 目录下没有 .txt 文档：{DATA_DIR}")

    groups = _split_by_document(docs)
    all_chunks = [c for _, _, chunks in groups for c in chunks]
    texts = [c.page_content for c in all_chunks]

    # 批量向量化（一次 API 调用处理所有文本，比逐个快）
    vectors = get_embeddings().embed_documents(texts)

    with SessionLocal() as db:
        # 重建策略：清空旧的（简单可靠；量大时可改增量）
        db.execute(delete(DocumentChunk))
        db.execute(delete(DocumentRecord))

        # 文档记录 + 知识块（含向量）：一篇文档只写它自己的块
        vec_idx = 0
        for name, chars, chunks in groups:
            record = DocumentRecord(name=name, chars=chars, chunk_count=len(chunks))
            db.add(record)
            db.flush()  # 拿到 record.id
            for chunk in chunks:
                db.add(
                    DocumentChunk(
                        document_id=record.id,
                        content=chunk.page_content,
                        embedding=vectors[vec_idx],
                    )
                )
                vec_idx += 1
        db.commit()

    _rebuild_bm25(texts)

    return {"documents": len(groups), "chunks": len(all_chunks)}


# ============ 检索 ============
def search(question: str, k: int = 3) -> list[str]:
    """向量检索：问题向量化 → pgvector 余弦距离排序 → 返回前 k 段正文"""
    query_vec = get_embeddings().embed_query(question)
    # <=> 是 pgvector 的"余弦距离"算子：越小越相关
    sql = text(
        "SELECT content FROM document_chunks "
        "ORDER BY embedding <=> CAST(:q AS vector) LIMIT :k"
    )
    with SessionLocal() as db:
        rows = db.execute(sql, {"q": json.dumps(query_vec), "k": k}).fetchall()
    return [r[0] for r in rows]


def search_bm25(question: str, k: int = 3) -> list[str]:
    """BM25 关键词检索：精确匹配，找回向量检索漏掉的（工号/专有名词等）"""
    if _bm25 is None:
        return []
    scores = _bm25.get_scores(list(jieba.cut(question)))
    ranked_idx = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:k]
    return [_bm25_chunks[i] for i in ranked_idx if scores[i] > 0]


def search_hybrid(question: str, k: int = 3, recall_k: int = 10) -> list[str]:
    """混合检索：向量（语义）+ BM25（关键词）→ RRF 融合 → 返回 top k。
    降级策略：BM25 不可用 → 纯向量；关闭开关 → 纯向量。"""
    vector_results = search(question, k=recall_k)
    if not USE_HYBRID or not _BM25_AVAILABLE:
        return vector_results[:k]

    bm25_results = search_bm25(question, k=recall_k)
    return rrf_fuse(vector_results, bm25_results, k=k)


# ============ 增删改查 ============
def search_hybrid_with_sources(question: str, k: int = 3) -> list[dict]:
    """为实际命中的知识块附上真实文档来源，保持混合检索排序。"""
    ranked_texts = search_hybrid(question, k=k)
    if not ranked_texts:
        return []
    with SessionLocal() as db:
        rows = db.execute(
            select(DocumentChunk.id, DocumentChunk.document_id, DocumentRecord.name, DocumentChunk.content)
            .join(DocumentRecord, DocumentRecord.id == DocumentChunk.document_id)
            .where(DocumentChunk.content.in_(ranked_texts)).order_by(DocumentChunk.id)
        ).all()
    by_content = {}
    for chunk_id, document_id, name, content in rows:
        by_content.setdefault(content, {
            "chunk_id": chunk_id, "document_id": document_id,
            "document_name": name, "content": content,
        })
    return [dict(by_content[content]) for content in ranked_texts if content in by_content]


def list_documents(limit: int | None = None, offset: int = 0) -> list[dict]:
    """列出知识库文档（从数据库查，支持分页）"""
    stmt = select(DocumentRecord).order_by(DocumentRecord.id).offset(offset)
    if limit:
        stmt = stmt.limit(limit)
    with SessionLocal() as db:
        records = db.execute(stmt).scalars().all()
    return [
        {"id": r.id, "name": r.name, "characters": r.chars, "chunks": r.chunk_count,
         "created_at": str(r.created_at)[:19] if r.created_at else ""}
        for r in records
    ]


def delete_document(doc_id: int) -> str:
    """删除文档：删数据库记录 + 知识块 + 物理文件 + 重建 BM25 索引"""
    with SessionLocal() as db:
        record = db.get(DocumentRecord, doc_id)
        if record is None:
            raise FileNotFoundError(f"文档 id={doc_id} 不存在")
        name = record.name
        db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == doc_id))
        db.delete(record)
        db.commit()

    # 删物理文件（data 目录）
    path = os.path.join(DATA_DIR, name)
    if os.path.exists(path):
        os.remove(path)

    # 重建内存 BM25（从数据库剩余文本重建，不重新向量化）
    with SessionLocal() as db:
        texts = db.execute(select(DocumentChunk.content)).scalars().all()
    _rebuild_bm25(texts)

    return name


def add_document_file(filename: str, content: str) -> None:
    """保存上传的文档到 data 目录，并重建索引"""
    safe_name = os.path.basename(filename)
    path = os.path.join(DATA_DIR, safe_name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    rebuild_index()
