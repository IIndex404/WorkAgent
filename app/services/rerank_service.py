"""
重排序服务：调用硅基流动 Rerank API 给检索结果精排
==================================================
为什么需要？（面试必答）
  向量检索是"粗筛"（快但糙），Rerank 是"精排"（慢但准）。
  生产级 RAG 标配两段式：粗筛 Top-10 → Rerank → 精排 Top-3。

设计要点（生产级思维）：
  1. 失败自动降级：Rerank 不可用（没密钥/网络差/模型未开通）→ 返回原顺序，
     不阻断主流程（RAG 照样能答，只是质量略降）
  2. 粗筛多捞、精排少留：给 Rerank 留出挑选空间
"""

import json
import urllib.request

from app.config import EMBEDDING_API_KEY, RERANK_BASE_URL, RERANK_MODEL, USE_RERANK


def rerank(query: str, documents: list[str], top_n: int = 3) -> list[dict]:
    """调用 rerank 接口，返回分数最高的 top_n 条。
    返回：[{"index": 0, "relevance_score": 0.9}, ...]（已按分数降序）"""
    body = json.dumps(
        {
            "model": RERANK_MODEL,
            "query": query,
            "documents": documents,
            "top_n": top_n,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        RERANK_BASE_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {EMBEDDING_API_KEY}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data.get("results", [])
