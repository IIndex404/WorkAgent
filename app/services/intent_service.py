"""
意图识别服务：结构化输出的企业应用
==================================
让模型把"用户问题"分类成结构化结果（用 with_structured_output）。

用途：
  1. RAG 路由：判断要不要查知识库 → 闲聊直接回答，省成本省延迟
  2. 演示 with_structured_output 在项目里的真实用法（面试点）

注意（之前踩过的坑）：
  method="function_calling"：DeepSeek 不支持 json_schema 输出格式，
  用函数调用方式最稳（OpenAI/DeepSeek 都支持）。
"""

from typing import Literal

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from app.core.llm import get_llm


class QuestionIntent(BaseModel):
    """问题的结构化分类结果"""

    category: Literal["company_policy", "chat", "calculation", "weather", "other"] = Field(
        description="问题类别：company_policy=公司制度咨询；chat=闲聊；calculation=数学计算；weather=天气；other=其他"
    )
    needs_knowledge_base: bool = Field(
        description="是否需要查询公司知识库才能回答：制度类问题为 true；闲聊/通用知识为 false"
    )
    summary: str = Field(description="用一句话概括用户想问什么")


_INTENT_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", "你是问题分类器。请把用户问题分类，并判断是否需要查询公司知识库。"),
        ("human", "问题：{question}"),
    ]
)


def classify_question(question: str) -> QuestionIntent:
    """对问题做结构化分类（强制按 QuestionIntent 格式输出）"""
    chain = _INTENT_PROMPT | get_llm(temperature=0).with_structured_output(
        QuestionIntent, method="function_calling"
    )
    return chain.invoke({"question": question})
