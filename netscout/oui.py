"""IEEE OUI vendor lookup.

Downloads the full IEEE OUI registry (~6MB, ~40,000 vendors) and parses it
into an in-memory dict for fast MAC → vendor lookups.
"""
import sys
import urllib.request
from datetime import datetime

from . import config

OUI_DB: dict = {}

# Minimal fallback if the full DB hasn't been downloaded yet
_FALLBACK = {
    "00:50:56": "VMware", "00:0c:29": "VMware",
    "b8:27:eb": "Raspberry Pi", "dc:a6:32": "Raspberry Pi",
    "e4:5f:01": "Raspberry Pi", "00:17:88": "Philips Hue",
    "00:11:32": "Synology", "74:44:01": "Ubiquiti",
    "00:27:22": "Ubiquiti", "04:18:d6": "Ubiquiti",
}


def load() -> int:
    """Parse oui.txt into OUI_DB. Returns the entry count."""
    global OUI_DB
    if not config.OUI_FILE.exists():
        print(f"[oui] {config.OUI_FILE} not found — download via UI",
              file=sys.stderr, flush=True)
        return 0

    count = 0
    new_db = {}
    with open(config.OUI_FILE, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if "(hex)" not in line:
                continue
            parts = line.split("(hex)")
            if len(parts) != 2:
                continue
            raw = parts[0].strip().replace("-", ":").lower()
            if len(raw) == 6:
                prefix = f"{raw[0:2]}:{raw[2:4]}:{raw[4:6]}"
            else:
                prefix = raw
            vendor = parts[1].strip()
            if prefix and vendor:
                new_db[prefix] = vendor
                count += 1
    OUI_DB = new_db
    print(f"[oui] Loaded {count:,} entries from {config.OUI_FILE}",
          file=sys.stderr, flush=True)
    return count


def download() -> tuple[bool, str]:
    """Download the latest IEEE OUI database. Returns (success, message)."""
    url = "https://standards-oui.ieee.org/oui/oui.txt"
    print(f"[oui] Downloading {url}…", file=sys.stderr, flush=True)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "NetScout/1.0"})
        with urllib.request.urlopen(req, timeout=60) as response:
            data = response.read()
        config.OUI_FILE.parent.mkdir(parents=True, exist_ok=True)
        config.OUI_FILE.write_bytes(data)
        kb = config.OUI_FILE.stat().st_size // 1024
        print(f"[oui] Downloaded {kb} KB", file=sys.stderr, flush=True)
        load()
        return True, f"Loaded {len(OUI_DB):,} vendors"
    except Exception as e:
        print(f"[oui] Download failed: {e}", file=sys.stderr, flush=True)
        return False, str(e)


def lookup(mac: str) -> str:
    """Look up vendor for a MAC address."""
    if not mac or mac == "unknown":
        return "Unknown"
    prefix = mac[:8].lower()
    if OUI_DB:
        return OUI_DB.get(prefix, "Unknown")
    return _FALLBACK.get(prefix, "Unknown")


def status() -> dict:
    """Return UI-facing status info for the OUI database."""
    if not config.OUI_FILE.exists():
        return {"loaded": len(OUI_DB), "file_exists": False, "file_size_kb": 0, "file_date": None}
    st = config.OUI_FILE.stat()
    return {
        "loaded": len(OUI_DB),
        "file_exists": True,
        "file_size_kb": st.st_size // 1024,
        "file_date": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d"),
    }
