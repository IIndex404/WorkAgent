"""
混合检索核心测试（纯函数，不需要数据库/网络，可离线跑）
======================================================
测试 RRF 融合算法：两路排名（向量+BM25）合并重排是否正确。
"""

from app.services.document_service import rrf_fuse


def test_rrf_fuse_puts_both_ranked_first():
    """两路都排前面的文档得分最高"""
    vector = ["A", "B", "C", "D"]   # 向量检索排名：A 第1，B 第2...
    bm25 = ["B", "D", "E"]          # BM25 排名：B 第1，D 第2...

    result = rrf_fuse(vector, bm25, k=3)

    # B 在两路都排前列（1/61 + 1/62）→ 总分最高，必须是第 1
    assert result[0] == "B"
    assert result == ["B", "D", "A"]   # D 两路都有 > A 单路第1
    assert len(result) == 3            # 只取 top 3


def test_rrf_fuse_deduplicates():
    """同一段文字在两路都出现时只算一次"""
    result = rrf_fuse(["X", "Y"], ["X", "Z"], k=2)
    assert result[0] == "X"          # X 两路都有
    assert len(result) == 2


def test_rrf_fuse_empty_bm25():
    """BM25 没结果时退回向量结果"""
    result = rrf_fuse(["A", "B", "C"], [], k=2)
    assert result == ["A", "B"]
