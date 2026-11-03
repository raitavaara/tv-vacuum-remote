"""The contract between the web server and a device.

app.py only talks to these two classes. To support another brand, subclass one, fill in the
few methods marked "implement", and register it in devices/__init__.py. Nothing else changes.
"""
import threading
import time

# The buttons the page can send. They are brand-neutral; a TV driver maps them to its own codes.
KEYS = ("power", "up", "down", "left", "right", "ok", "back", "home", "source", "info",
        "vol_up", "vol_down", "mute", "ch_up", "ch_down", "play", "pause", "rewind", "ff")


class Tv:
    """Generic TV bookkeeping: on/standby/off state, "turning on" window, opening an app after power-on.

    Implement in a subclass:
        poll() -> "on" | "standby" | "off"      cheap check, called every few seconds
        send_key(key, hold=0)                    one of KEYS (hold = seconds to hold it)
        launch_app(app_id)                       open an app
        wake()                                   switch on from standby/off (Wake-on-LAN, CEC, cloud call...)
    Optional: warm() to open a connection early, close() to drop it.
    """
    WAKE_LIMIT = 25      # seconds to wait for the TV to come on before telling the page it failed

    def __init__(self, cfg, on_change):
        self.cfg = cfg
        self.name = cfg.get("name", "TV")
        self.host = cfg.get("host")
        self.apps = cfg.get("apps", [])
        self.on_change = on_change
        self.state = "off"
        self.waking_until = 0.0
        self.wake_started = 0.0
        self.wake_failed_at = 0.0
        self.opening = None
        self.open_failed_at = 0.0
        self.lock = threading.Lock()

    # ----- implement -----
    def poll(self): raise NotImplementedError
    def send_key(self, key, hold=0): raise NotImplementedError
    def launch_app(self, app_id): raise NotImplementedError
    def wake(self): raise NotImplementedError
    def warm(self): pass
    def close(self): pass
    def tend(self): pass         # called every poll cycle (keep connections alive, etc.)

    # ----- generic -----
    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        while True:
            try:
                new = self.poll()
            except Exception:
                new = "off"
            if new != self.state:
                self.state = new
                if new == "on":
                    self.waking_until = 0
                self.on_change()
            if self.waking_until and time.time() > self.waking_until:
                self.waking_until = 0
                if self.state != "on":
                    self.wake_failed_at = time.time()
                    self.opening = None
                self.on_change()
            try:
                self.tend()
            except Exception:
                pass
            time.sleep(2 if self.waking_until else 4)

    def view(self):
        now = time.time()
        waking = bool(self.waking_until) and self.state != "on"
        return {"name": self.name, "state": self.state, "on": self.state == "on", "waking": waking,
                "apps": self.apps,
                "wake_age": round(now - self.wake_started) if waking else None,
                "wake_limit": self.WAKE_LIMIT,
                "wake_failed": bool(self.wake_failed_at) and now - self.wake_failed_at < 15 and self.state != "on",
                "opening": self.opening if waking or self.state == "on" else None,
                "open_failed": bool(self.open_failed_at) and now - self.open_failed_at < 15}

    def key(self, key):
        if key not in KEYS:
            raise ValueError("Unknown button")
        if self.state == "off":
            raise RuntimeError("Still turning on" if self.waking_until else "The TV is off")
        with self.lock:
            self.send_key(key)

    def power(self, on):
        if on:
            if self.state == "on":
                return
            self.wake()
            self.wake_started = time.time()
            self.wake_failed_at = 0.0
            self.waking_until = self.wake_started + self.WAKE_LIMIT
            self.on_change()
            threading.Thread(target=self._keep_waking, daemon=True).start()
        elif self.state == "on":
            with self.lock:
                self.send_key("power", hold=1.5)    # drivers decide what a held power key means
            self.state = "standby"
            self.on_change()

    def _keep_waking(self):
        """Some TVs miss the first wake packet: try again every few seconds until it's on."""
        end = time.time() + self.WAKE_LIMIT - 5
        while time.time() < end and self.state != "on":
            time.sleep(3)
            if self.state != "on":
                self.wake()

    def app(self, app_id):
        """Open an app; if the TV is off, switch it on first and open the app once it's up."""
        if not any(a["id"] == app_id for a in self.apps):
            raise ValueError("Unknown app")
        if self.state == "on":
            self.launch_app(app_id)
            return
        self.opening = next(a["name"] for a in self.apps if a["id"] == app_id)
        self.open_failed_at = 0.0
        self.power(True)
        threading.Thread(target=self._launch_when_on, args=(app_id,), daemon=True).start()

    def _launch_when_on(self, app_id):
        end = time.time() + 40
        while time.time() < end and self.state != "on":
            time.sleep(1)
        if self.state == "on":
            time.sleep(4)     # let the home screen settle
            try:
                self.launch_app(app_id)
            except Exception:
                self.open_failed_at = time.time()
        self.opening = None
        self.on_change()


class Vacuum:
    """A robot vacuum. Implement in a subclass:

        start()                      begin talking to the robot (start threads)
        refresh()                    fetch fresh status (non-blocking)
        command(cmd)                 cmd in COMMANDS; raise RuntimeError("...") if it can't be done
        view() -> dict               see VIEW_FIELDS; None when the vacuum isn't set up
    Call self.on_change() whenever view() would return something new, and
    self.on_event(kind, text) for things worth an alert ("vacuum", "vacuum_done").
    """
    COMMANDS = ("start", "pause", "resume", "stop", "dock", "home")
    VIEW_FIELDS = ("name", "connected", "status", "battery", "bin_full", "error", "cleaning", "paused", "docked")

    def __init__(self, cfg, on_change, on_event):
        self.cfg, self.on_change, self.on_event = cfg, on_change, on_event

    def start(self): raise NotImplementedError
    def refresh(self): pass
    def command(self, cmd): raise NotImplementedError
    def view(self): raise NotImplementedError
