"""Pretend devices for trying the page without hardware: DEMO=1 python -m uvicorn app:app"""
import threading
import time

from .base import KEYS, Tv, Vacuum


class FakeTv(Tv):
    def __init__(self, cfg, on_change):
        super().__init__({"name": "Demo TV", "apps": [{"id": "1", "name": "YouTube", "bg": "#ff0000", "fg": "#fff"},
                                                       {"id": "2", "name": "Movies", "bg": "#222", "fg": "#fff"}],
                          **cfg}, on_change)
        self.sent = []

    def poll(self): return self.state
    def send_key(self, key, hold=0): self.sent.append(key)
    def launch_app(self, app_id): self.sent.append("app:" + app_id)

    def wake(self):
        def on():
            time.sleep(1.5)
            self.state = "on"
        threading.Thread(target=on, daemon=True).start()


class FakeVacuum(Vacuum):
    def __init__(self, cfg, on_change, on_event):
        super().__init__(cfg, on_change, on_event)
        self.phase, self.battery = "charge", 100

    def start(self): pass

    def command(self, cmd):
        if cmd not in self.COMMANDS:
            raise ValueError("Unknown command")
        self.phase = {"start": "run", "resume": "run", "pause": "pause", "stop": "stop",
                      "dock": "dock", "home": "dock"}[cmd]
        self.on_change()

    def view(self):
        p = self.phase
        names = {"charge": "On the dock", "run": "Cleaning", "pause": "Paused", "stop": "Stopped", "dock": "Going home"}
        return {"name": self.cfg.get("name", "Demo vacuum"), "connected": True, "live": True, "status": names[p],
                "phase": p, "battery": self.battery, "bin_full": False, "error": None,
                "cleaning": p == "run", "paused": p in ("pause", "stop"), "docked": p == "charge"}
