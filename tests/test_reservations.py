import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Barrier

import pytest
from fastapi.testclient import TestClient

from app.main import SEOUL, create_app

NOW = datetime(2030, 5, 6, 8, 0, tzinfo=SEOUL)
DAY = "2030-05-06"


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "roompick.sqlite3"


@pytest.fixture
def client(db_path):
    with TestClient(create_app(db_path, clock=lambda: NOW, seed=False)) as client:
        yield client


def payload(**overrides):
    return {"room_id": 1, "date": DAY, "start_time": "09:00", "end_time": "10:00",
            "title": "제품 회의", "organizer": "테스트 예약자", "attendees": 4, **overrides}


def test_create_list_detail_cancel_and_rebook(client):
    assert client.get("/api/reservations", params={"date": DAY}).json() == []
    created = client.post("/api/reservations", json=payload())
    assert created.status_code == 201
    booking = created.json()
    assert booking["created_at"].endswith("+09:00")
    assert client.get(f"/api/reservations/{booking['id']}").json() == booking
    schedule = client.get("/api/schedule", params={"date": DAY}).json()
    assert schedule["reservations"] == [booking]
    assert schedule["timezone"] == "Asia/Seoul"
    assert [r["capacity"] for r in schedule["rooms"]] == [4, 8, 12]
    assert client.delete(f"/api/reservations/{booking['id']}").status_code == 204
    assert client.get("/api/reservations", params={"date": DAY}).json() == []
    assert client.get(f"/api/reservations/{booking['id']}").status_code == 404
    assert client.delete(f"/api/reservations/{booking['id']}").status_code == 404
    assert client.post("/api/reservations", json=payload()).status_code == 201


@pytest.mark.parametrize("start,end", [("09:00", "10:00"), ("09:30", "10:30"),
                                       ("10:30", "11:30"), ("09:00", "11:00"),
                                       ("10:00", "10:30")])
def test_overlap_rejected(client, start, end):
    assert client.post("/api/reservations", json=payload(start_time="09:30", end_time="11:00")).status_code == 201
    response = client.post("/api/reservations", json=payload(start_time=start, end_time=end))
    assert response.status_code == 409
    assert "다른 예약" in response.json()["detail"]
    assert len(client.get("/api/reservations", params={"date": DAY}).json()) == 1


def test_adjacency_room_and_date_boundaries(client):
    for override in [dict(start_time="09:30", end_time="10:30"),
                     dict(start_time="09:00", end_time="09:30"),
                     dict(start_time="10:30", end_time="11:00"),
                     dict(start_time="16:00", end_time="18:00"),
                     dict(room_id=2), dict(date="2030-05-07")]:
        assert client.post("/api/reservations", json=payload(**override)).status_code == 201


@pytest.mark.parametrize("overrides", [
    {"start_time": "08:30", "end_time": "09:30"},
    {"start_time": "17:30", "end_time": "18:30"},
    {"start_time": "09:15", "end_time": "10:00"},
    {"start_time": "09:00", "end_time": "09:15"},
    {"start_time": "09:00", "end_time": "11:30"},
    {"start_time": "10:00", "end_time": "09:00"},
    {"start_time": "10:00", "end_time": "10:00"},
    {"start_time": "09:00:00"}, {"start_time": "9:00"}, {"end_time": "24:00"},
    {"date": "2030-02-30"}, {"date": "20300506"}, {"date": "2030-5-6"},
    {"date": "2030-05-05"}, {"attendees": 5}, {"attendees": 0}, {"attendees": -1},
    {"attendees": 1.5}, {"attendees": True}, {"attendees": "2"},
    {"room_id": 99}, {"room_id": True}, {"title": "   "}, {"organizer": "\n\t"},
    {"title": "x" * 81}, {"organizer": "x" * 31}, {"unexpected": "value"},
])
def test_invalid_input(client, overrides):
    response = client.post("/api/reservations", json=payload(**overrides))
    assert response.status_code == 422, response.text
    assert isinstance(response.json()["detail"], str)
    assert client.get("/api/reservations", params={"date": DAY}).json() == []


@pytest.mark.parametrize("field", list(payload()))
def test_required_fields(client, field):
    data = payload()
    del data[field]
    assert client.post("/api/reservations", json=data).status_code == 422


@pytest.mark.parametrize("room_id,capacity", [(1, 4), (2, 8), (3, 12)])
def test_room_capacity(client, room_id, capacity):
    assert client.post("/api/reservations", json=payload(room_id=room_id, attendees=capacity + 1)).status_code == 422
    assert client.post("/api/reservations", json=payload(room_id=room_id, attendees=capacity)).status_code == 201


def test_seoul_time_and_exact_now(db_path):
    # 00:00 UTC is 09:00 Seoul; equality is valid, one second later is past.
    clock = [datetime(2030, 5, 6, 0, 0, tzinfo=timezone.utc)]
    with TestClient(create_app(db_path, clock=lambda: clock[0], seed=False)) as client:
        assert client.get("/api/schedule").json()["date"] == DAY
        first = client.post("/api/reservations", json=payload())
        assert first.status_code == 201
        client.delete(f"/api/reservations/{first.json()['id']}")
        clock[0] = datetime(2030, 5, 6, 0, 0, 1, tzinfo=timezone.utc)
        assert client.post("/api/reservations", json=payload()).status_code == 422
        assert client.post("/api/reservations", json=payload(start_time="09:30", end_time="10:00")).status_code == 201


def test_default_date_uses_seoul_not_utc(db_path):
    clock = lambda: datetime(2030, 5, 5, 16, 0, tzinfo=timezone.utc)
    with TestClient(create_app(db_path, clock=clock, seed=False)) as client:
        assert client.get("/api/schedule").json()["date"] == DAY


def test_seed_runs_once_and_cancellations_stay_cancelled(db_path):
    with TestClient(create_app(db_path, clock=lambda: NOW)) as client:
        original = client.get("/api/schedule").json()["reservations"]
        assert len(original) == 6
        client.delete(f"/api/reservations/{original[0]['id']}")
        custom = client.post("/api/reservations", json=payload(date="2030-05-07")).json()
    with TestClient(create_app(db_path, clock=lambda: datetime(2030, 5, 7, 8, tzinfo=SEOUL))) as restarted:
        assert restarted.get("/api/reservations", params={"date": DAY}).json() == original[1:]
        assert restarted.get("/api/schedule").json()["reservations"] == [custom]
        for booking in original[1:] + [custom]:
            restarted.delete(f"/api/reservations/{booking['id']}")
    with TestClient(create_app(db_path, clock=lambda: NOW)) as restarted:
        assert restarted.get("/api/schedule").json()["reservations"] == []


def test_simultaneous_requests_across_app_instances(db_path):
    apps = [create_app(db_path, clock=lambda: NOW, seed=False) for _ in range(2)]
    with TestClient(apps[0]) as first, TestClient(apps[1]) as second:
        barrier = Barrier(12)
        def book(index):
            barrier.wait()
            return [first, second][index % 2].post("/api/reservations", json=payload()).status_code
        with ThreadPoolExecutor(max_workers=12) as pool:
            results = list(pool.map(book, range(12)))
        assert results.count(201) == 1
        assert results.count(409) == 11
        assert len(first.get("/api/reservations", params={"date": DAY}).json()) == 1
    with sqlite3.connect(db_path) as db:
        assert db.execute("SELECT count(*) FROM reservation_slots").fetchone()[0] == 2
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_db_slot_constraint_and_cancel_cleanup(client, db_path):
    created = client.post("/api/reservations", json=payload()).json()
    with sqlite3.connect(db_path) as db:
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("INSERT INTO reservation_slots VALUES (?,?,?,?)", (1, DAY, 540, created["id"]))
    client.delete(f"/api/reservations/{created['id']}")
    with sqlite3.connect(db_path) as db:
        assert db.execute("SELECT count(*) FROM reservation_slots").fetchone()[0] == 0


def test_busy_database_returns_clear_error(client, db_path):
    with sqlite3.connect(db_path) as blocker:
        blocker.execute("BEGIN IMMEDIATE")
        response = client.post("/api/reservations", json=payload())
        assert response.status_code == 503
        assert "잠시 후" in response.json()["detail"]
    assert client.post("/api/reservations", json=payload()).status_code == 201


def test_read_errors_and_safe_input_storage(client):
    assert client.get("/api/reservations").status_code == 422
    assert client.get("/api/schedule", params={"date": "bad"}).status_code == 422
    dangerous = "<img src=x onerror=alert(1)>"
    response = client.post("/api/reservations", json=payload(title=dangerous, organizer="' OR 1=1; --"))
    assert response.status_code == 201
    assert response.json()["title"] == dangerous
    assert client.get("/").status_code == 200
    assert "script-src 'self'" in client.get("/").headers["content-security-policy"]
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/api/health").json() == {"status": "ok"}
