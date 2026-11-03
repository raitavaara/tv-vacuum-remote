"""Find a Roomba and read its local password. Run with the robot on the same network:

    python tools/roomba_pair.py              # list robots found on the network
    python tools/roomba_pair.py 192.168.1.51 # read the password for that robot

Before the second form: stand next to the robot, hold the HOME button until it plays a tone
(about 2 s) - it then hands out the password for about a minute. This writes ROOMBA_BLID and
ROOMBA_PASSWORD to data/secrets.env and the address to data/config.json.
"""
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import settings  # noqa: E402


async def main(ip):
    from roombapy import RoombaDiscovery, RoombaPassword
    robots = await RoombaDiscovery().get_all(timeout=5)
    if not ip:
        for r in robots:
            print(f"{r.ip}  {r.robot_name}  ({r.sku})")
        print("Found %d robot(s). Run again with the address to pair." % len(robots) if robots else "No robot found.")
        return
    blid = next((r.blid for r in robots if r.ip == ip), None)
    if not blid:
        sys.exit("That address wasn't found by discovery. Check the robot is on Wi-Fi.")
    print("Hold the HOME button until the robot plays a tone...")
    end, password = time.time() + 120, None
    while time.time() < end and not password:
        try:
            password = await RoombaPassword(ip).get_password()
        except Exception:
            await asyncio.sleep(2)
    if not password:
        sys.exit("Didn't get a password. Hold the button until the tone and try again.")
    settings.set_secret("ROOMBA_BLID", blid)
    settings.set_secret("ROOMBA_PASSWORD", password)
    cfg = settings.config()
    cfg.setdefault("vacuum", {"driver": "roomba", "name": "Vacuum"})["host"] = ip
    settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
    settings.path("config.json").write_text(json.dumps(cfg, indent=2))
    print(f"Done. Saved to {settings.DATA_DIR}")

asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else None))
