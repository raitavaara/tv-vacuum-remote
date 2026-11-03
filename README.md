# TV + vacuum remote

A small local web server that puts a **TV remote** and a **robot vacuum** on one phone-friendly page,
talking to the devices directly over your home network (no brand cloud, no accounts).

It was extracted from a larger home dashboard that has run daily in one household. The reference
drivers are for a **Samsung Tizen TV** and an **iRobot Roomba**; the point of this repo is the
structure, so you can swap in your own brands (LG, Sony, Philips, Dreame, Roborock, ...) by writing
one small driver file.

```
phone / browser ──HTTP + live updates (SSE)──► app.py (FastAPI) ──► devices/samsung_tv.py ──► TV
                                                                └─► devices/roomba.py     ──► vacuum
```

* `app.py` – the REST API, the live-update stream and the page. Knows nothing about brands.
* `devices/base.py` – **the contract**: `Tv` and `Vacuum` base classes. Read this first.
* `devices/samsung_tv.py`, `devices/roomba.py` – reference drivers.
* `devices/fake.py` – pretend devices, so you can work on the page with no hardware.
* `static/index.html` – one self-contained page, no build step, no framework.
* `tools/` – helpers to find your devices and read the Roomba's password.

## Try it in 30 seconds (no hardware)

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
DEMO=1 .venv/bin/python -m uvicorn app:app --port 8080
# open http://localhost:8080
.venv/bin/python -m pytest tests
```

## Use it with the real devices

1. Copy `config.example.json` to `data/config.json` and fill in your devices. Give both devices a fixed
   address in your router (DHCP reservation). Everything personal lives in `data/`, which git ignores.
2. **Samsung TV:** `python tools/tv_info.py <tv-ip>` shows its name and MAC. In the TV's network settings
   enable *Power On with Mobile* (needed for Wake-on-LAN). The first button press makes the TV show an
   **Allow** prompt – accept it; the token is saved to `data/tv_token.txt`.
3. **Roomba:** `python tools/roomba_pair.py` lists robots; then hold the robot's HOME button until it
   beeps and run `python tools/roomba_pair.py <robot-ip>`. This stores the local password in
   `data/secrets.env`.
4. Run: `.venv/bin/python -m uvicorn app:app --host 0.0.0.0 --port 8080`, or install `deploy/tv-vacuum-remote.service`
   to start it at boot.

> **Security:** there is no login. Run it on your home network only and never forward the port to the internet.

## Adding your own brand

Copy the closest driver, rename it, and implement the methods marked *implement* in `devices/base.py`:

| TV (`Tv`) | what it does |
|---|---|
| `poll()` | return `"on"`, `"standby"` or `"off"` (called every ~4 s, keep it fast) |
| `send_key(key, hold=0)` | `key` is one of the neutral names in `base.KEYS` (`up`, `ok`, `vol_up`, ...) – map them to your TV's codes |
| `launch_app(app_id)` | open an app |
| `wake()` | switch on from standby/off (Wake-on-LAN, HDMI-CEC, a vendor API...) |

The base class already handles the "Turning on…" window, retrying wake-ups, and opening an app after
power-on. For vacuums, implement `start`, `refresh`, `command` and `view` and call `on_change()` when
something changed. Then register the driver in `devices/__init__.py` and set `"driver": "yourbrand"` in
`config.json`.

Useful starting points for other brands: [`python-roborock`](https://github.com/humbertogontijo/python-roborock),
[`aiowebostv`](https://github.com/home-assistant-libs/aiowebostv) (LG), [`bravia-tv`](https://github.com/dcnielsen90/python-bravia-tv) (Sony),
[`pyatv`](https://github.com/postlund/pyatv) (Apple TV), and the [Home Assistant integrations](https://github.com/home-assistant/core/tree/dev/homeassistant/components)
for protocol details.

## Hard-won notes from the Samsung/Roomba drivers

* The Samsung remote websocket takes ~1.5 s to open, so the driver keeps it open while the remote is in
  use and pings it. A connection opened while the TV is still booting can go deaf – open a fresh one.
* Some Samsung models ignore a short power press; holding it ~1.5 s switches them off.
* From deep standby only Wake-on-LAN works, and the first packets get missed: resend every few seconds.
* A Roomba stays awake while anyone is connected to its MQTT port, so the driver connects only on demand
  (page open, a command, while cleaning) and lets go when docked.
* Only one local MQTT client at a time is allowed by many Roomba firmwares – close the iRobot app when testing.

## API

| | |
|---|---|
| `GET /api/state` | `{tv, vacuum, alerts}` |
| `GET /api/events` | same, pushed as server-sent events whenever something changes |
| `POST /api/tv/key {"key": "ok"}` / `/api/tv/power {"on": true}` / `/api/tv/app {"id": "..."}` / `/api/tv/warm` | TV |
| `POST /api/vacuum/{start,pause,resume,stop,dock,home}` / `/api/vacuum-refresh` / `GET /api/vacuum` | vacuum |

Errors: 400 bad request, 409 the device refuses right now (e.g. TV off), 502 the device can't be reached.

MIT licensed.
