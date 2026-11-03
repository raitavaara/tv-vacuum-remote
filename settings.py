"""Where this home's settings live. Nothing personal is ever kept in the code folder.

    $REMOTE_DATA   if set, else   ./data/

    data/config.json    which devices you have: addresses, names, driver   (see config.example.json)
    data/secrets.env    passwords/tokens, one NAME='value' per line        (see secrets.example.env)
    data/tv_token.txt   written by the Samsung driver when the TV is paired
"""
import json
import os
from pathlib import Path

DATA_DIR = Path(os.environ.get("REMOTE_DATA") or Path(__file__).resolve().parent / "data")


def path(name):
    return DATA_DIR / name


def config():
    try:
        return json.loads(path("config.json").read_text())
    except (OSError, ValueError):
        return {}


def secret(name, default=""):
    """A value from the environment, else from data/secrets.env."""
    if os.environ.get(name):
        return os.environ[name]
    try:
        for line in path("secrets.env").read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                if key.strip() == name:
                    return value.strip().strip("'\"")
    except OSError:
        pass
    return default


def set_secret(name, value):
    """Add or replace one line in secrets.env (file kept private)."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    f = path("secrets.env")
    lines = f.read_text().splitlines() if f.exists() else []
    lines = [l for l in lines if l.split("=", 1)[0].strip() != name] + [f"{name}='{value}'"]
    fd = os.open(f, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as out:
        out.write("\n".join(lines) + "\n")
