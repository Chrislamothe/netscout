"""Persistent storage for NetScout device data.

Single JSON file at config.DATA_FILE. Holds:
  devices         — mac → device dict
  extra_subnets   — list of CIDR strings
  switches        — list of switch configs
  aps             — list of AP configs
  last_scan       — ISO timestamp
"""
import json
from . import config


def load() -> dict:
    """Load the full data file, returning sensible defaults if missing."""
    if config.DATA_FILE.exists():
        try:
            return json.loads(config.DATA_FILE.read_text())
        except Exception:
            pass
    return {"devices": {}, "last_scan": None}


def save(data: dict) -> None:
    """Atomically write data to disk."""
    config.DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = config.DATA_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(config.DATA_FILE)


def get_extra_subnets() -> list:
    """Get configured extra subnets, falling back to config default."""
    saved = load().get("extra_subnets")
    if saved is not None:
        return saved
    return list(config.EXTRA_SUBNETS)


def set_extra_subnets(subnets: list) -> None:
    data = load()
    data["extra_subnets"] = subnets
    save(data)


def get_switches() -> list:
    return load().get("switches", list(config.DEFAULT_SWITCHES))


def set_switches(switches: list) -> None:
    data = load()
    data["switches"] = switches
    save(data)


def get_aps() -> list:
    return load().get("aps", list(config.DEFAULT_APS))


def set_aps(aps: list) -> None:
    data = load()
    data["aps"] = aps
    save(data)
