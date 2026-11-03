"""Print what a Samsung TV says about itself (name, MAC address) so you can fill in config.json.

    python tools/tv_info.py 192.168.1.50

The TV must be on. Give it a fixed address in your router (DHCP reservation) so config.json stays right.
"""
import sys

import requests

info = requests.get(f"http://{sys.argv[1]}:8001/api/v2/", timeout=4).json()
d = info.get("device", {})
print("name:", d.get("name"), "\nmodel:", d.get("modelName"), "\nmac (wifi):", d.get("wifiMac"),
      "\nPowerState:", d.get("PowerState"))
print("For a wired TV, the MAC is in the TV's Settings > Support > About / Network status.")
