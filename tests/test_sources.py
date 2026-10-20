import asyncio

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models import DocumentChunk, DocumentRecord
from app.services import document_service, rag_service


def test_sources_map_to_real_documents_and_preserve_search_order(monkeypatch):
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine, tables=[DocumentRecord.__table__, DocumentChunk.__table__])
    with Session(engine) as db:
        handbook = DocumentRecord(name='员工手册.txt')
        training = DocumentRecord(name='培训办法.txt')
        db.add_all([handbook, training])
        db.flush()
        db.add_all([DocumentChunk(document_id=handbook.id, content='年假5天'),
                    DocumentChunk(document_id=training.id, content='培训一周')])
        db.commit()
    monkeypatch.setattr(document_service, 'SessionLocal', lambda: Session(engine))
    monkeypatch.setattr(document_service, 'search_hybrid', lambda *args, **kwargs: ['培训一周', '年假5天'])
    sources = document_service.search_hybrid_with_sources('公司制度')
    assert [source['document_name'] for source in sources] == ['培训办法.txt', '员工手册.txt']
    assert [source['content'] for source in sources] == ['培训一周', '年假5天']
    assert all(source['document_id'] and source['chunk_id'] for source in sources)
    engine.dispose()


def test_rerank_preserves_document_identity_when_reordering(monkeypatch):
    sources = [dict(document_id=1, chunk_id=1, document_name='A.txt', content='甲'),
               dict(document_id=2, chunk_id=2, document_name='B.txt', content='乙')]
    monkeypatch.setattr(document_service, 'search_hybrid_with_sources', lambda *args, **kwargs: sources)
    monkeypatch.setattr(rag_service, 'USE_RERANK', True)
    monkeypatch.setattr(rag_service, 'rerank', lambda *args, **kwargs: [{'index': 1}, {'index': 0}])
    ranked = rag_service.search_with_sources('问题')
    assert [item['document_name'] for item in ranked] == ['B.txt', 'A.txt']
    assert [item['citation'] for item in ranked] == [1, 2]
    assert 'citation' not in sources[0]
