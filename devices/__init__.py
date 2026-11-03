"""Driver registry. Add a new brand here: write devices/<brand>.py (see base.py), then list it below."""
import os

from .base import KEYS, Tv, Vacuum  # noqa: F401


def make_tv(cfg, on_change):
    driver = cfg.get("driver", "samsung")
    if driver == "fake":
        from .fake import FakeTv
        return FakeTv(cfg, on_change)
    if driver == "samsung":
        from .samsung_tv import SamsungTv
        return SamsungTv(cfg, on_change)
    # elif driver == "lg":  from .lg_tv import LgTv; return LgTv(cfg, on_change)
    raise ValueError(f"Unknown TV driver: {driver}")


def make_vacuum(cfg, on_change, on_event):
    driver = cfg.get("driver", "roomba")
    if driver == "fake":
        from .fake import FakeVacuum
        return FakeVacuum(cfg, on_change, on_event)
    if driver == "roomba":
        from .roomba import Roomba
        return Roomba(cfg, on_change, on_event)
    # elif driver == "dreame": ...
    raise ValueError(f"Unknown vacuum driver: {driver}")
