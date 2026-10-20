"""
模型工厂
========
统一创建 LLM 和 Embedding 对象。
好处：全项目只在这里接触"模型具体是什么"，换模型只改这一个文件。
"""

from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from app.config import (
    EMBEDDING_API_KEY,
    EMBEDDING_BASE_URL,
    EMBEDDING_MODEL,
    EMBEDDING_PROVIDER,
    LLM_API_KEY,
    LLM_BASE_URL,
    LLM_MODEL,
)


def get_llm(temperature: float = 0.3):
    """创建聊天模型。temperature 越低越稳定（业务默认 0.3）。"""
    if not LLM_API_KEY:
        raise RuntimeError("未配置 LLM_API_KEY，请复制 .env.example 为 .env 并填写密钥")
    return ChatOpenAI(
        model=LLM_MODEL,
        base_url=LLM_BASE_URL,
        api_key=LLM_API_KEY,
        temperature=temperature,
    )


def get_embeddings():
    """创建向量化模型（RAG 用）。"""
    local_tei = EMBEDDING_PROVIDER == "tei"
    if not local_tei and not EMBEDDING_API_KEY:
        raise RuntimeError("未配置 EMBEDDING_API_KEY，RAG 功能需要向量化模型")
    return OpenAIEmbeddings(
        model=EMBEDDING_MODEL,
        base_url=EMBEDDING_BASE_URL,
        # TEI 本地服务不需要密钥；SDK 要求 api_key 非空，使用本地占位值。
        api_key=EMBEDDING_API_KEY or "local-not-required",
        # BGE 接口接收原始文本，不能使用 OpenAI 的 tiktoken token ID。
        check_embedding_ctx_length=False,
        model_kwargs={"encoding_format": "float"},
        chunk_size=16 if local_tei else 1000,
    )
