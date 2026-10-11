from __future__ import annotations

import logging
import os
import re
import sqlite3
from contextlib import asynccontextmanager, contextmanager
from datetime import date, datetime, time
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

ROOT = Path(__file__).resolve().parent.parent
SEOUL = ZoneInfo("Asia/Seoul")
ROOMS = [
    (1, "포커스룸", 4, "작은 팀의 깊이 있는 대화", "화이트보드,모니터,Wi-Fi", "green"),
    (2, "아이디어룸", 8, "함께 생각하고, 함께 만드는 공간", "화이트보드,대형 모니터,화상회의", "blue"),
    (3, "라운지룸", 12, "더 많은 사람, 더 넓은 가능성", "프로젝터,화상회의,스피커", "purple"),
]
SCHEMA = """
CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS rooms (
    id INTEGER PRIMARY KEY, name TEXT NOT NULL, capacity INTEGER NOT NULL,
    description TEXT NOT NULL, facilities TEXT NOT NULL, color TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reservations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    room_id INTEGER NOT NULL REFERENCES rooms(id), date TEXT NOT NULL,
    start_min INTEGER NOT NULL CHECK(start_min >= 540 AND start_min % 30 = 0),
    end_min INTEGER NOT NULL CHECK(end_min <= 1080 AND end_min % 30 = 0),
    title TEXT NOT NULL CHECK(length(trim(title)) BETWEEN 1 AND 80),
    organizer TEXT NOT NULL CHECK(length(trim(organizer)) BETWEEN 1 AND 30),
    attendees INTEGER NOT NULL CHECK(attendees >= 1), created_at TEXT NOT NULL,
    CHECK(end_min - start_min BETWEEN 30 AND 120)
);
CREATE INDEX IF NOT EXISTS reservations_day ON reservations(date, room_id, start_min);
CREATE TABLE IF NOT EXISTS reservation_slots (
    room_id INTEGER NOT NULL REFERENCES rooms(id), date TEXT NOT NULL,
    minute INTEGER NOT NULL,
    reservation_id INTEGER NOT NULL REFERENCES reservations(id) ON DELETE CASCADE,
    PRIMARY KEY(room_id, date, minute)
);
"""


class ReservationInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    room_id: int = Field(strict=True, ge=1)
    date: str = Field(strict=True)
    start_time: str = Field(strict=True)
    end_time: str = Field(strict=True)
    title: str = Field(strict=True, min_length=1, max_length=80)
    organizer: str = Field(strict=True, min_length=1, max_length=30)
    attendees: int = Field(strict=True, ge=1)


def parse_day(value: str) -> date:
    try:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError
        return date.fromisoformat(value)
    except ValueError:
        raise HTTPException(422, "날짜를 YYYY-MM-DD 형식으로 정확히 입력해 주세요.") from None


def minutes(value: str) -> int:
    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
        raise HTTPException(422, "시간을 HH:MM 형식으로 정확히 입력해 주세요.")
    hour, minute = map(int, value.split(":"))
    return hour * 60 + minute


def hhmm(value: int) -> str:
    return f"{value // 60:02d}:{value % 60:02d}"


def serialize(row: sqlite3.Row) -> dict:
    item = dict(row)
    item["start_time"] = hhmm(item.pop("start_min"))
    item["end_time"] = hhmm(item.pop("end_min"))
    return item


@contextmanager
def connection(path: Path):
    db = sqlite3.connect(path, timeout=5, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    try:
        yield db
    finally:
        if db.in_transaction:
            db.rollback()
        db.close()


def insert_reservation(db, room_id, day, start, end, title, organizer, attendees, now):
    cursor = db.execute(
        "INSERT INTO reservations(room_id,date,start_min,end_min,title,organizer,attendees,created_at) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (room_id, day, start, end, title, organizer, attendees, now.isoformat()),
    )
    reservation_id = cursor.lastrowid
    # The unique slot key also protects the invariant across independent server processes.
    db.executemany(
        "INSERT INTO reservation_slots VALUES (?,?,?,?)",
        [(room_id, day, minute, reservation_id) for minute in range(start, end, 30)],
    )
    return reservation_id


def initialize(path: Path, now: datetime, seed: bool):
    path.parent.mkdir(parents=True, exist_ok=True)
    with connection(path) as db:
        db.execute("PRAGMA journal_mode = WAL")
        db.executescript(SCHEMA)
        db.execute("BEGIN IMMEDIATE")
        if not db.execute("SELECT 1 FROM metadata WHERE key='initialized'").fetchone():
            db.executemany("INSERT INTO rooms VALUES (?,?,?,?,?,?)", ROOMS)
            if seed:
                # Historical sample bookings on the first Seoul day are intentional.
                samples = [
                    (1, 570, 630, "이번 주를 여는 팀 미팅", "김민지", 4),
                    (1, 810, 870, "새로운 서비스 이야기", "이서준", 3),
                    (2, 600, 690, "프로덕트 아이디어 워크숍", "박지우", 6),
                    (2, 900, 960, "디자인 리뷰", "정하은", 5),
                    (3, 660, 720, "팀 리더 싱크업", "최도윤", 10),
                    (3, 840, 930, "다음 분기, 함께 그리기", "윤서연", 8),
                ]
                for room, start, end, title, organizer, attendees in samples:
                    insert_reservation(db, room, now.date().isoformat(), start, end,
                                       title, organizer, attendees, now)
            db.execute("INSERT INTO metadata VALUES ('initialized', ?)", (now.isoformat(),))
        db.commit()


def create_app(db_path: str | Path | None = None,
               clock: Callable[[], datetime] | None = None, seed: bool = True) -> FastAPI:
    path = Path(db_path or os.environ.get("ROOMPICK_DB", ROOT / "data" / "roompick.sqlite3")).resolve()
    get_time = clock or (lambda: datetime.now(SEOUL))

    def now():
        return get_time().astimezone(SEOUL)

    @asynccontextmanager
    async def lifespan(_app):
        initialize(path, now(), seed)
        yield

    app = FastAPI(title="룸픽 API", version="1.0.0", lifespan=lifespan,
                  docs_url=None, redoc_url=None)
    app.state.db_path = path

    @app.middleware("http")
    async def headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; font-src 'self'; connect-src 'self'; "
            "object-src 'none'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        )
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request, exc):
        labels = {"room_id": "회의실", "date": "날짜", "start_time": "시작 시간",
                  "end_time": "종료 시간", "title": "회의 제목 (1~80자)",
                  "organizer": "예약자 이름 (1~30자)", "attendees": "참석 인원 (1명 이상)"}
        fields = list(dict.fromkeys(labels.get(str(e["loc"][-1]), "입력값") for e in exc.errors()))
        return JSONResponse(status_code=422, content={"detail": f"{', '.join(fields)} 항목을 확인해 주세요. 필수 항목과 입력 형식을 확인해 주세요."})

    @app.exception_handler(sqlite3.OperationalError)
    async def db_error(_request, exc):
        if "locked" in str(exc) or "busy" in str(exc):
            return JSONResponse(status_code=503, content={"detail": "다른 예약을 처리하고 있어요. 잠시 후 다시 시도해 주세요."}, headers={"Retry-After": "2"})
        logging.exception("Database operation failed", exc_info=exc)
        return JSONResponse(status_code=500, content={"detail": "데이터를 불러오지 못했어요. 잠시 후 다시 시도해 주세요."})

    @app.exception_handler(Exception)
    async def unexpected_error(_request, exc):
        logging.exception("Unexpected server error", exc_info=exc)
        return JSONResponse(status_code=500, content={"detail": "서버에 문제가 생겼어요. 잠시 후 다시 시도해 주세요."})

    def room_list(db):
        result = [dict(r) for r in db.execute("SELECT * FROM rooms ORDER BY id")]
        for room in result:
            room["facilities"] = room["facilities"].split(",")
        return result

    @app.get("/api/rooms")
    def rooms():
        with connection(path) as db:
            return room_list(db)

    @app.get("/api/schedule")
    def schedule(date: str | None = None):
        current = now()
        day = parse_day(date).isoformat() if date else current.date().isoformat()
        with connection(path) as db:
            return {"date": day, "timezone": "Asia/Seoul", "server_time": current.isoformat(),
                    "rooms": room_list(db), "reservations": [serialize(r) for r in db.execute(
                        "SELECT * FROM reservations WHERE date=? ORDER BY start_min,id", (day,))]}

    @app.get("/api/reservations")
    def reservations(date: str):
        day = parse_day(date).isoformat()
        with connection(path) as db:
            return [serialize(r) for r in db.execute(
                "SELECT * FROM reservations WHERE date=? ORDER BY start_min,id", (day,))]

    @app.get("/api/reservations/{reservation_id}")
    def reservation(reservation_id: int):
        with connection(path) as db:
            row = db.execute("SELECT * FROM reservations WHERE id=?", (reservation_id,)).fetchone()
            if row is None:
                raise HTTPException(404, "이미 취소되었거나 존재하지 않는 예약이에요.")
            return serialize(row)

    @app.post("/api/reservations", status_code=201)
    def create_reservation(payload: ReservationInput):
        day = parse_day(payload.date)
        start, end = minutes(payload.start_time), minutes(payload.end_time)
        if end <= start:
            raise HTTPException(422, "종료 시간은 시작 시간보다 늦어야 해요.")
        if start < 540 or end > 1080:
            raise HTTPException(422, "예약 가능 시간은 매일 09:00~18:00이에요.")
        if start % 30 or end % 30:
            raise HTTPException(422, "시작과 종료 시간은 30분 단위로 선택해 주세요.")
        if not 30 <= end - start <= 120:
            raise HTTPException(422, "한 번에 최소 30분, 최대 2시간까지 예약할 수 있어요.")
        with connection(path) as db:
            # Acquire the write lock BEFORE checking availability. Covers all workers/processes.
            db.execute("BEGIN IMMEDIATE")
            current = now()
            if datetime.combine(day, time(start // 60, start % 60), tzinfo=SEOUL) < current:
                raise HTTPException(422, "이미 지난 시간은 예약할 수 없어요. 앞으로의 시간을 선택해 주세요.")
            room = db.execute("SELECT * FROM rooms WHERE id=?", (payload.room_id,)).fetchone()
            if room is None:
                raise HTTPException(422, "회의실을 다시 선택해 주세요.")
            if payload.attendees > room["capacity"]:
                raise HTTPException(422, f"{room['name']}은 최대 {room['capacity']}명까지 이용할 수 있어요.")
            overlap = db.execute(
                "SELECT 1 FROM reservations WHERE room_id=? AND date=? AND start_min<? AND end_min>?",
                (payload.room_id, payload.date, end, start),
            ).fetchone()
            if overlap:
                raise HTTPException(409, "선택한 시간에 다른 예약이 있어요. 최신 일정을 확인하고 다른 시간을 선택해 주세요.")
            try:
                reservation_id = insert_reservation(db, payload.room_id, payload.date, start, end,
                                                    payload.title, payload.organizer, payload.attendees, current)
            except sqlite3.IntegrityError:
                raise HTTPException(409, "다른 예약이 먼저 완료되었어요. 다른 시간을 선택해 주세요.") from None
            row = db.execute("SELECT * FROM reservations WHERE id=?", (reservation_id,)).fetchone()
            db.commit()
            return serialize(row)

    @app.delete("/api/reservations/{reservation_id}", status_code=204)
    def cancel_reservation(reservation_id: int):
        with connection(path) as db:
            db.execute("BEGIN IMMEDIATE")
            cursor = db.execute("DELETE FROM reservations WHERE id=?", (reservation_id,))
            if cursor.rowcount == 0:
                raise HTTPException(404, "이미 취소되었거나 존재하지 않는 예약이에요.")
            db.commit()  # Foreign-key cascade releases every occupied slot atomically.
        return Response(status_code=204)

    @app.get("/api/health")
    def health():
        with connection(path) as db:
            db.execute("SELECT 1 FROM metadata").fetchone()
        return {"status": "ok"}

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(ROOT / "static" / "index.html")

    app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
    return app


app = create_app()
