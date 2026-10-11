"""Real HTTP, two independent server processes, and a complete stop/restart."""
import os
import socket
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from threading import Barrier
from zoneinfo import ZoneInfo

import httpx

ROOT = Path(__file__).resolve().parents[1]


@contextmanager
def server(db_path):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    environment = {**os.environ, "ROOMPICK_DB": str(db_path)}
    process = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port), "--log-level", "error"],
                               cwd=ROOT, env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=15, trust_env=False) as client:
            for _ in range(100):
                if process.poll() is not None:
                    raise AssertionError(process.stderr.read().decode(errors="replace"))
                try:
                    if client.get("/api/health").status_code == 200:
                        break
                except httpx.TransportError:
                    pass
                time.sleep(0.1)
            else:
                raise AssertionError("Server did not become ready")
            yield client
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        process.stderr.close()


def test_real_process_concurrency_and_persistence(tmp_path):
    db_path = tmp_path / "persistent.sqlite3"
    day = (datetime.now(ZoneInfo("Asia/Seoul")) + timedelta(days=2)).date().isoformat()
    payload = {"room_id": 2, "date": day, "start_time": "16:00", "end_time": "18:00",
               "title": "실제 프로세스 검증", "organizer": "테스트", "attendees": 8}
    with server(db_path) as first, server(db_path) as second:
        barrier = Barrier(10)
        def book(index):
            barrier.wait()
            return [first, second][index % 2].post("/api/reservations", json=payload)
        with ThreadPoolExecutor(max_workers=10) as pool:
            responses = list(pool.map(book, range(10)))
        assert sorted(r.status_code for r in responses) == [201] + [409] * 9
        saved = next(r.json() for r in responses if r.status_code == 201)
        seed_before = first.get("/api/schedule").json()["reservations"]
    # Both processes are now stopped. A brand-new process must read the same data.
    with server(db_path) as restarted:
        assert restarted.get("/api/reservations", params={"date": day}).json() == [saved]
        assert restarted.get("/api/schedule").json()["reservations"] == seed_before
        assert restarted.delete(f"/api/reservations/{saved['id']}").status_code == 204
        recreated = restarted.post("/api/reservations", json=payload)
        assert recreated.status_code == 201
        assert recreated.json()["id"] != saved["id"]
