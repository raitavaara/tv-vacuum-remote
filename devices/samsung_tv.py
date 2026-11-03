"""Samsung Tizen TV (2016+), local network only, no Samsung cloud.

State: the TV's REST endpoint on :8001 answers only while it is on or in network standby.
Buttons: websocket remote on :8002, paired once (the TV shows an Allow prompt the first time;
the token is stored in data/tv_token.txt). Power on: Wake-on-LAN (needs "Power On with Mobile"
enabled in the TV's network settings). Power off: holding the power key ~1.5 s (a short press is
ignored by some models).
"""
import re
import socket
import time

import requests
from samsungtvws import SamsungTVWS

import settings
from .base import Tv

IDLE_CLOSE = 600     # drop the remote connection after this long unused (s)
KEYMAP = {"power": "KEY_POWER", "up": "KEY_UP", "down": "KEY_DOWN", "left": "KEY_LEFT", "right": "KEY_RIGHT",
          "ok": "KEY_ENTER", "back": "KEY_RETURN", "home": "KEY_HOME", "source": "KEY_SOURCE",
          "info": "KEY_INFO", "vol_up": "KEY_VOLUP", "vol_down": "KEY_VOLDOWN", "mute": "KEY_MUTE",
          "ch_up": "KEY_CHUP", "ch_down": "KEY_CHDOWN", "play": "KEY_PLAY", "pause": "KEY_PAUSE",
          "rewind": "KEY_REWIND", "ff": "KEY_FF"}
COLOUR = re.compile(r"#[0-9a-fA-F]{3,8}")
# Find an app's id: curl http://<tv>:8001/api/v2/applications/<id>  answers with the name if installed.


def clean_app(a):
    out = {"id": str(a["id"]), "name": a["name"]}
    for k in ("bg", "fg"):
        if COLOUR.fullmatch(str(a.get(k, ""))):
            out[k] = a[k]
    return out


class SamsungTv(Tv):
    def __init__(self, cfg, on_change):
        super().__init__(cfg, on_change)
        self.mac = cfg.get("mac", "")
        self.apps = [clean_app(a) for a in cfg.get("apps", [])]
        self.remote = None
        self.last_used = 0.0
        self.pinged = 0.0

    def poll(self):
        try:
            info = requests.get(f"http://{self.host}:8001/api/v2/", timeout=1.5).json()
            return "on" if info.get("device", {}).get("PowerState", "on") == "on" else "standby"
        except (requests.RequestException, ValueError):
            return "off"

    # --- connection upkeep: opening the websocket takes ~1.5 s, so keep it ready ---
    def _close(self):
        try:
            self.remote.close()
        except Exception:
            pass
        self.remote = None

    close = _close

    def _ws(self, action):
        for attempt in (1, 2):       # a stale connection fails once, then we reconnect
            try:
                if not self.remote:
                    self.remote = SamsungTVWS(host=self.host, port=8002, name="Remote Dashboard", timeout=4,
                                              key_press_delay=0, token_file=str(settings.path("tv_token.txt")))
                    self.remote.open()
                action(self.remote)
                self.last_used = time.time()
                return
            except Exception:
                self._close()
                if attempt == 2:
                    raise

    def warm(self):
        if self.state == "on":
            self.last_used = time.time()
            import threading

            def go():
                try:
                    with self.lock:
                        self._ws(lambda r: None)
                except Exception:
                    pass
            threading.Thread(target=go, daemon=True).start()

    def tend(self):
        with self.lock:
            if not self.remote:
                return
            if self.state != "on" or time.time() - self.last_used > IDLE_CLOSE:
                self._close()
            elif time.time() - self.pinged > 20:
                self.pinged = time.time()
                try:
                    self.remote.connection.ping()
                except Exception:
                    self._close()

    # --- the contract ---
    def send_key(self, key, hold=0):
        code = KEYMAP[key]
        if key == "power" and hold:
            self._close()      # a connection opened while the TV was starting can go deaf: start fresh
        self._ws(lambda r: r.hold_key(code, hold) if hold else r.send_key(code))

    def launch_app(self, app_id):
        try:               # the TV's REST call opens installed apps most reliably
            if requests.post(f"http://{self.host}:8001/api/v2/applications/{app_id}", timeout=4).ok:
                return
        except requests.RequestException:
            pass
        with self.lock:
            self._ws(lambda r: r.run_app(app_id))

    def wake(self):
        packet = bytes.fromhex("ff" * 6 + self.mac.replace(":", "") * 16)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            for _ in range(3):
                for addr in ("255.255.255.255", self.host.rsplit(".", 1)[0] + ".255", self.host):
                    for port in (9, 7):      # which port a TV listens on varies
                        s.sendto(packet, (addr, port))
                time.sleep(0.1)
        if self.state == "standby":          # network standby: the remote can also switch it on
            try:
                with self.lock:
                    self.send_key("power")
                    self._close()
            except Exception:
                pass
