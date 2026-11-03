"""iRobot Roomba (e/i/j series, firmware 3.x) over the local MQTT connection, no iRobot cloud.

The robot keeps its lights on while anyone is connected, so this driver connects only when it has
a reason to: at start-up, when the page asks for a refresh, while the robot is busy, and for a
couple of minutes after it docks (to catch "finished"). Otherwise it lets the robot sleep.
Credentials (ROOMBA_BLID, ROOMBA_PASSWORD) come from data/secrets.env; get them with
tools/roomba_pair.py.
"""
import asyncio
import threading
import time

import settings
from .base import Vacuum

SETTLE = 120        # stay connected this long after docking
STATE_WAIT = 10     # seconds to wait for the first state after connecting

PHASES = {"charge": "Charging", "run": "Cleaning", "new": "Cleaning", "resume": "Cleaning",
          "spot": "Spot cleaning", "hmMidMsn": "Recharging", "recharge": "Recharging", "stuck": "Stuck",
          "hmUsrDock": "Going home", "dock": "Going home", "dockend": "Going home", "hmPostMsn": "Going home",
          "stop": "Stopped", "cancelled": "Stopped", "pause": "Paused", "evac": "Emptying bin",
          "chargingerror": "Dock unplugged", "completed": "Done"}
CLEANING = {"run", "new", "resume", "spot", "hmMidMsn", "recharge"}
BUSY = CLEANING | {"stuck", "pause", "stop", "cancelled", "hmUsrDock", "dock", "dockend", "hmPostMsn", "evac"}


class Roomba(Vacuum):
    def __init__(self, cfg, on_change, on_event):
        super().__init__(cfg, on_change, on_event)
        self.host = cfg.get("host", "")
        self.name = cfg.get("name", "Vacuum")
        self.blid, self.password = settings.secret("ROOMBA_BLID"), settings.secret("ROOMBA_PASSWORD")
        self.enabled = bool(self.host and self.blid and self.password)
        self.loop = self.client = self.wake = self.conn_lock = None
        self.reported, self.checked, self.reachable = {}, None, None
        self.last = None
        self.was_cleaning = False
        self.problem = None
        self.bin_alerted = False
        self.hold_until = 0

    def start(self):
        if not self.enabled:
            print("roomba: host, ROOMBA_BLID or ROOMBA_PASSWORD missing - vacuum is off")
            return
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.wake, self.conn_lock = asyncio.Event(), asyncio.Lock()
        self.loop.run_until_complete(self._main())

    @property
    def connected(self):
        return bool(self.client and self.client.connected)

    async def _connect(self):
        from roombapy import RoombaClient
        async with self.conn_lock:
            if self.connected:
                return
            self.client = RoombaClient(self.host, self.blid, self.password)
            self.client.register_on_message_callback(lambda *_: self._on_message())
            try:
                await asyncio.wait_for(self.client.connect(), 30)
            except Exception:
                self.reachable = False
                self._changed()
                raise
            self.reachable = True
        end = time.time() + STATE_WAIT
        while time.time() < end and "cleanMissionStatus" not in self._fresh():
            await asyncio.sleep(0.5)

    async def _disconnect(self):
        async with self.conn_lock:
            if self.client:
                try:
                    await self.client.disconnect()
                except Exception:
                    pass
                self.client = None
        self._changed()

    def _fresh(self):
        return (self.client.master_state.get("state", {}).get("reported", {}) if self.client else {}) or {}

    def _on_message(self):
        rep = self._fresh()
        if rep:
            self.reported = {**self.reported, **rep}
            self.checked = time.time()
        self._changed()

    async def _main(self):
        docked_since = None
        while True:
            try:
                await self._connect()
            except Exception as e:
                print(f"roomba: can't reach the robot ({e})")
            while self.connected:
                if self._phase() in BUSY:
                    docked_since = None
                elif docked_since is None:
                    docked_since = time.time()
                if docked_since is not None and time.time() > self.hold_until \
                        and time.time() - docked_since >= (SETTLE if self.was_cleaning else 0):
                    break
                self._changed()
                try:
                    await asyncio.wait_for(self.wake.wait(), 30)
                except asyncio.TimeoutError:
                    pass
                self.wake.clear()
            docked_since = None
            await self._disconnect()
            await self.wake.wait()       # sleep until a refresh or command needs the robot
            self.wake.clear()

    def _phase(self):
        return (self.reported.get("cleanMissionStatus") or {}).get("phase", "")

    def view(self):
        if not self.enabled:
            return None
        rep, phase = self.reported, self._phase()
        known = bool(rep) and self.reachable is not False
        error = None
        if self.connected and (getattr(self.client, "error_code", 0) or 0):
            error = getattr(self.client, "error_message", None) or f"error {self.client.error_code}"
        status = "Offline" if not known else PHASES.get(phase, phase.capitalize() or "Idle")
        battery = rep.get("batPct")
        if status == "Charging" and battery == 100:
            status = "On the dock"
        return {"name": rep.get("name") or self.name, "connected": known, "live": self.connected,
                "checked": self.checked, "status": status, "phase": phase, "battery": battery,
                "bin_full": bool((rep.get("bin") or {}).get("full")), "error": error,
                "cleaning": phase in CLEANING, "paused": phase in ("pause", "stop", "cancelled", "stuck"),
                "docked": known and phase in ("charge", "evac", "chargingerror", "")}

    def _changed(self):
        v = self.view()
        if v == self.last:
            return
        self._events(v)
        self.last = v
        self.on_change()

    def _events(self, v):
        if not v or not v["connected"] or not v["live"]:
            return
        name = v["name"]
        problem = v["error"] or ("stuck" if v["phase"] == "stuck" else None)
        if problem and problem != self.problem:
            self.on_event("vacuum", f"{name} needs help: {problem}")
        self.problem = problem
        if v["bin_full"] and not self.bin_alerted:
            self.on_event("vacuum", f"{name}'s bin is full")
        self.bin_alerted = v["bin_full"]
        if v["cleaning"]:
            self.was_cleaning = True
        elif self.was_cleaning and v["docked"]:
            self.was_cleaning = False
            self.on_event("vacuum_done", f"{name} finished cleaning and is back on the dock")

    def refresh(self):
        if self.loop and not self.connected:
            self.loop.call_soon_threadsafe(self.wake.set)

    def command(self, cmd):
        if cmd not in self.COMMANDS:
            raise ValueError("Unknown command")
        if not self.loop:
            raise RuntimeError("The robot vacuum isn't set up")

        async def go():
            try:
                await self._connect()
            except Exception:
                raise RuntimeError("The vacuum isn't reachable right now")
            if cmd == "home":
                if self._phase() in CLEANING:
                    await self.client.send_command("stop")
                    await asyncio.sleep(1.5)
                await self.client.send_command("dock")
            else:
                await self.client.send_command(cmd)
            self.hold_until = time.time() + 60
            self.wake.set()
        asyncio.run_coroutine_threadsafe(go(), self.loop).result(timeout=45)
        time.sleep(1)
        self._changed()
