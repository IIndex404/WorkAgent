"""用少量制度问题检查回答是否包含预期关键词。运行：python evaluate.py。此脚本需要可用的数据库、向量服务和对话模型，不代表完整的问答质量评估。"""

import os
import sys

# 确保能 import app 包（从项目根目录运行）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services import rag_service  # noqa: E402

# ============ 测试集（问题 + 期望回答里出现的关键词） ============
# 企业做法：专家标注标准答案；这里用关键词命中法演示（简单可跑）
TEST_SET = [
    {"question": "公司几点下班？", "keywords": ["18:00", "下午"]},
    {"question": "公积金公司交多少？", "keywords": ["12%"]},
    {"question": "年假最长多少天？", "keywords": ["15"]},
    {"question": "请假需要提前多久？", "keywords": ["提前", "一天"]},
    {"question": "怎么申请晋升？", "keywords": ["答辩", "年限"]},
    {"question": "新员工有培训吗？", "keywords": ["培训", "一周"]},
]


def main() -> None:
    print("=" * 64)
    print("RAG 系统评测（测试集 + 关键词命中）")
    print("=" * 64)
    total_score = 0.0
    finished = 0
    for i, item in enumerate(TEST_SET, 1):
        try:
            answer = rag_service.routed_answer(item["question"])
        except Exception as e:
            print(f"[{i}] 问：{item['question']}")
            print(f"    ❌ 运行出错：{type(e).__name__}: {e}")
            continue
        hits = [kw for kw in item["keywords"] if kw in answer]
        score = len(hits) / len(item["keywords"])
        total_score += score
        finished += 1
        print(f"[{i}] 问：{item['question']}")
        print(f"    答：{answer[:60]}...")
        print(f"    命中关键词：{hits}  得分：{score:.0%}")
        print()
    print("-" * 64)
    if finished:
        print(f"📊 总分：{total_score / finished:.0%}（{finished}/{len(TEST_SET)} 题完成）")
    else:
        print("❌ 没有题目跑成功，检查密钥配置")
    print("提示：改切分/加Rerank/换模型后重跑本脚本，分数涨了=改对了")


if __name__ == "__main__":
    main()
