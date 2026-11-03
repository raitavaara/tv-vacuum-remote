import os
import sys
from pathlib import Path

os.environ["DEMO"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402
import app as server  # noqa: E402

client = TestClient(server.app)


def test_state_has_both_devices():
    s = client.get("/api/state").json()
    assert s["tv"]["name"] and s["vacuum"]["status"] == "On the dock"


def test_tv_off_refuses_keys_then_power_on():
    assert client.post("/api/tv/key", json={"key": "ok"}).status_code == 409
    client.post("/api/tv/power", json={"on": True})
    import time
    time.sleep(0.2)
    server.tv.state = "on"
    assert client.post("/api/tv/key", json={"key": "ok"}).status_code == 200
    assert client.post("/api/tv/key", json={"key": "nope"}).status_code == 400
    assert client.post("/api/tv/app", json={"id": "1"}).status_code == 200
    assert client.post("/api/tv/app", json={"id": "999"}).status_code == 400


def test_vacuum_commands():
    assert client.post("/api/vacuum/start").json()["vacuum"]["cleaning"] is True
    assert client.post("/api/vacuum/home").json()["vacuum"]["status"] == "Going home"
    assert client.post("/api/vacuum/explode").status_code == 400


def test_page_served():
    assert "<title>" in client.get("/").text
