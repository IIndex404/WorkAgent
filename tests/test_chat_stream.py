import asyncio
import json
from types import SimpleNamespace

from fastapi.testclient import TestClient
from langchain_core.runnables import RunnableLambda

from app.main import app
from app.routers import chat
from app.services import rag_service


def test_missing_model_key_returns_actionable_error(monkeypatch):
    def missing_key():
        raise RuntimeError('未配置 LLM_API_KEY，请填写密钥')

    monkeypatch.setattr(chat, 'get_llm', missing_key)
    response = TestClient(app).post('/chat/stream', json={'message': '你好'})
    assert response.status_code == 503
    assert 'LLM_API_KEY' in response.json()['detail']


def test_stream_preserves_newlines_and_whitespace(monkeypatch):
    async def stream(*args):
        yield {'event': 'message', 'data': '第一行\n'}
        yield {'event': 'message', 'data': '  第二行 '}

    monkeypatch.setattr(chat, 'get_llm', lambda: object())
    monkeypatch.setattr(rag_service, 'routed_stream_events', stream)
    response = TestClient(app).post('/chat/stream', json={'message': '测试'})
    frames = response.text.replace('\r\n', '\n').split('\n\n')
    chunks = []
    for frame in frames:
        if frame.startswith('event: message\n'):
            data = next(line[6:] for line in frame.split('\n') if line.startswith('data: '))
            chunks.append(json.loads(data))
    assert ''.join(chunks) == '第一行\n  第二行 '
    assert 'event: end' in response.text


def test_stream_failure_reports_error_without_leaking_details(monkeypatch):
    async def stream(*args):
        yield {'event': 'message', 'data': '部分回答'}
        raise RuntimeError('private upstream details')

    monkeypatch.setattr(chat, 'get_llm', lambda: object())
    monkeypatch.setattr(rag_service, 'routed_stream_events', stream)
    response = TestClient(app).post('/chat/stream', json={'message': '测试'})
    assert response.status_code == 200
    assert 'event: error' in response.text
    assert 'private upstream details' not in response.text
    assert 'event: end' not in response.text


def test_stream_uses_retrieved_context_history_and_saves_completed_turn(monkeypatch):
    prompts, saved, cleaned = [], [], []
    monkeypatch.setattr(rag_service, '_history_text', lambda _: '用户：我入职一年')
    monkeypatch.setattr(rag_service, 'classify_question', lambda _: SimpleNamespace(needs_knowledge_base=True))
    sources = [{'citation': 1, 'document_id': 1, 'document_name': '员工手册.txt', 'chunk_id': 2, 'content': '入职满一年享有5天年假'}]
    monkeypatch.setattr(rag_service, 'search_with_sources', lambda *args, **kwargs: sources)

    async def llm(prompt):
        prompts.append(prompt.to_string())
        yield '你有'
        yield '5天年假。'

    monkeypatch.setattr(rag_service, 'get_llm', lambda **kwargs: RunnableLambda(llm))
    monkeypatch.setattr(rag_service, '_save_turn', lambda *args: saved.append(args))
    monkeypatch.setattr(rag_service, '_clean_history', lambda session: cleaned.append(session))

    async def collect():
        return ''.join([chunk async for chunk in rag_service.routed_stream('我能休几天？', 'regression-stream')])

    assert asyncio.run(collect()) == '你有5天年假。'
    assert '入职满一年享有5天年假' in prompts[0]
    assert '用户：我入职一年' in prompts[0]
    assert saved == [('regression-stream', '我能休几天？', '你有5天年假。', sources)]
    assert cleaned == ['regression-stream']
