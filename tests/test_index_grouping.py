"""
知识库切分分组测试（纯单元测试：不需要数据库、不需要 API 密钥）
==============================================================
这是"纯函数单测"的示范：
  因为 _split_by_document() 不碰数据库、不调 embedding API，
  所以它能在任何机器上、几毫秒内跑完（对比 test_document_service.py 必须起 Docker）。

★ 为什么要有这个文件（真实 bug 记录）：
  早期版本的 rebuild_index() 这么写：
      chunks = splitter.split_documents(docs)      # 所有文档的全部块，一个大列表
      for doc in docs:                             # 然后遍历每篇文档
          for chunk, vec in zip(chunks, vectors):  # 却把"全部块"都挂上去
              db.add(DocumentChunk(document_id=record.id, ...))
  结果：2 篇文档、实际共 16 块 → 数据库写入 32 行，且每篇文档都声称自己有 16 块。
  文档越多放大越狠（N 篇文档 = 每个块重复 N 遍）：检索会返回重复段落、
  浪费 token、后台显示的 chunk_count 也是假的。

  当时的测试为什么没抓到？因为 test_document_service.py 整体被 skip 掉了，
  而且切分逻辑埋在必须连数据库的 rebuild_index() 里，没法单独测。
  教训：**把逻辑从"必须连外部依赖"的地方抽出来，它才可测**。
"""

import pytest
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.services.document_service import _split_by_document


def _make_doc(name: str, marker: str, repeat: int) -> Document:
    """造一篇"整篇都是同一个标记"的假文档，用来判断某个块属于谁"""
    return Document(page_content=marker * repeat, metadata={"source": f"/tmp/{name}"})


def _make_unique_doc(name: str, tag: str, parts: int) -> Document:
    """造一篇"每段内容都不同"的假文档，用来检查有没有重复块"""
    body = "".join(f"{tag}第{j}段：这是用于测试的知识条目正文内容。" for j in range(parts))
    return Document(page_content=body, metadata={"source": f"/tmp/{name}"})


def test_groups_keep_document_order_and_names():
    """分组结果应保持顺序，文件名取 basename，字数分别正确"""
    docs = [_make_doc("甲.txt", "甲" * 10, 40), _make_doc("乙.txt", "乙" * 10, 10)]
    groups = _split_by_document(docs)

    assert [g[0] for g in groups] == ["甲.txt", "乙.txt"]
    assert [g[1] for g in groups] == [400, 100]


def test_each_document_only_gets_its_own_chunks():
    """★ 核心防回归：每篇文档的块里不能混进别的文档的内容"""
    docs = [_make_doc("甲.txt", "甲" * 10, 40), _make_doc("乙.txt", "乙" * 10, 10)]
    groups = _split_by_document(docs)
    jia_chunks, yi_chunks = groups[0][2], groups[1][2]

    assert all("乙" not in c.page_content for c in jia_chunks)
    assert all("甲" not in c.page_content for c in yi_chunks)


def test_chunk_counts_reflect_each_document_length():
    """长短不同的文档，块数就应该不同（旧 bug 会让两边都等于总块数）"""
    docs = [_make_doc("长.txt", "长" * 10, 40), _make_doc("短.txt", "短" * 10, 10)]
    groups = _split_by_document(docs)
    long_count, short_count = len(groups[0][2]), len(groups[1][2])

    assert long_count > short_count


def test_total_chunk_count_matches_direct_split():
    """分组不能凭空多出块、也不能丢块：总数应等于"不做分组、直接一次性切分"的结果"""
    docs = [_make_unique_doc("a.txt", "甲", 30), _make_unique_doc("b.txt", "乙", 45)]

    grouped_total = sum(len(cs) for _, _, cs in _split_by_document(docs))

    splitter = RecursiveCharacterTextSplitter(chunk_size=200, chunk_overlap=50)
    direct_total = len(splitter.split_documents(docs))

    assert grouped_total == direct_total


@pytest.mark.parametrize("n_docs", [1, 2, 5])
def test_no_duplication_for_any_document_count(n_docs: int):
    """无论几篇文档，块总数都不该被放大（旧 bug 会放大 n_docs 倍）"""
    docs = [_make_unique_doc(f"{i}.txt", f"第{i}篇", 30) for i in range(n_docs)]
    all_chunks = [c for _, _, cs in _split_by_document(docs) for c in cs]

    # 每段内容都不同 → (来源文件, 内容) 去重后数量应等于总数，即不存在重复块
    keys = [(c.metadata.get("source"), c.page_content) for c in all_chunks]
    assert len(keys) == len(set(keys))


def test_empty_document_list_returns_empty_groups():
    """没有文档时应返回空列表（由调用方决定报不报错）"""
    assert _split_by_document([]) == []
