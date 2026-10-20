import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.auth import create_access_token
from app.db import Base, get_db
from app.main import app
from app.models import ApprovalRecord, LeaveRequest, User


@pytest.fixture
def leave_client():
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine, tables=[User.__table__, LeaveRequest.__table__, ApprovalRecord.__table__])
    db = Session(engine)
    users = {}
    for username, role in [('alice', 'employee'), ('bob', 'employee'), ('reviewer', 'admin')]:
        user = User(username=username, role=role, password_hash='not-used-in-test')
        db.add(user)
        db.flush()
        users[username] = user
    db.commit()
    headers = {name: {'Authorization': 'Bearer ' + create_access_token(user)} for name, user in users.items()}

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    try:
        yield TestClient(app), headers, db
    finally:
        app.dependency_overrides.pop(get_db, None)
        db.close()
        engine.dispose()


def request_body(**changes):
    return dict({'leave_type': '年假', 'start_date': '2026-11-02', 'end_date': '2026-11-04', 'reason': '测试申请事由'}, **changes)


def create(client, headers, **changes):
    response = client.post('/leave/requests', json=request_body(**changes), headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def test_leave_endpoints_require_auth(leave_client):
    client, _, _ = leave_client
    assert client.get('/leave/requests').status_code == 401
    assert client.post('/leave/requests', json=request_body()).status_code == 401
    assert client.get('/admin/leave-requests').status_code == 401


def test_create_uses_authenticated_identity_and_counts_inclusive_days(leave_client):
    client, headers, _ = leave_client
    record = create(client, headers['alice'])
    assert record['applicant'] == 'alice'
    assert record['days'] == 3
    assert record['status'] == 'pending'
    assert record['reviewed_by'] is None
    assert client.post('/leave/requests', json=request_body(user_id=2), headers=headers['alice']).status_code == 422


@pytest.mark.parametrize('change', [{'end_date': '2026-11-01'}, {'reason': '   '}, {'leave_type': '任意类型'}])
def test_invalid_leave_inputs_rejected(leave_client, change):
    client, headers, _ = leave_client
    assert client.post('/leave/requests', json=request_body(**change), headers=headers['alice']).status_code == 422


def test_employee_cannot_read_other_employee_requests(leave_client):
    client, headers, _ = leave_client
    record = create(client, headers['alice'])
    assert client.get('/leave/requests', headers=headers['bob']).json() == []
    assert client.get(f"/leave/requests/{record['id']}", headers=headers['bob']).status_code == 404
    assert client.get(f"/leave/requests/{record['id']}", headers=headers['alice']).status_code == 200


def test_employee_cannot_review_even_with_a_forged_role_claim(leave_client):
    client, headers, db = leave_client
    record = create(client, headers['alice'])
    assert client.get('/admin/leave-requests', headers=headers['alice']).status_code == 403
    assert client.post(f"/admin/leave-requests/{record['id']}/review", json={'decision': 'approved'}, headers=headers['alice']).status_code == 403
    bob = db.execute(select(User).where(User.username == 'bob')).scalar_one()
    fake_admin = User(username=bob.username, role='admin')
    forged = {'Authorization': 'Bearer ' + create_access_token(fake_admin)}
    assert client.get('/admin/leave-requests', headers=forged).status_code == 403


def test_approve_is_visible_to_applicant_and_creates_one_audit_record(leave_client):
    client, headers, db = leave_client
    record = create(client, headers['alice'])
    path = f"/admin/leave-requests/{record['id']}/review"
    response = client.post(path, json={'decision': 'approved', 'comment': '同意，请交接工作'}, headers=headers['reviewer'])
    assert response.status_code == 200
    own = client.get('/leave/requests', headers=headers['alice']).json()[0]
    assert own['status'] == 'approved'
    assert own['reviewed_by'] == 'reviewer'
    assert own['review_comment'] == '同意，请交接工作'
    assert own['reviewed_at']
    assert client.post(path, json={'decision': 'rejected', 'comment': '重复操作'}, headers=headers['reviewer']).status_code == 409
    audit = db.execute(select(ApprovalRecord)).scalars().all()
    assert len(audit) == 1 and audit[0].status == 'approved'
    assert client.get('/admin/leave-requests?status=pending', headers=headers['reviewer']).json() == []


def test_rejection_requires_comment_and_allows_a_new_request(leave_client):
    client, headers, _ = leave_client
    record = create(client, headers['alice'])
    path = f"/admin/leave-requests/{record['id']}/review"
    assert client.post(path, json={'decision': 'rejected', 'comment': ' '}, headers=headers['reviewer']).status_code == 422
    response = client.post(path, json={'decision': 'rejected', 'comment': '请调整日期'}, headers=headers['reviewer'])
    assert response.status_code == 200 and response.json()['status'] == 'rejected'
    assert create(client, headers['alice'])['status'] == 'pending'


def test_pending_or_approved_period_cannot_overlap(leave_client):
    client, headers, _ = leave_client
    record = create(client, headers['alice'])
    assert client.post('/leave/requests', json=request_body(start_date='2026-11-04'), headers=headers['alice']).status_code == 409
    client.post(f"/admin/leave-requests/{record['id']}/review", json={'decision': 'approved'}, headers=headers['reviewer'])
    assert client.post('/leave/requests', json=request_body(), headers=headers['alice']).status_code == 409
    assert create(client, headers['bob'])['status'] == 'pending'
