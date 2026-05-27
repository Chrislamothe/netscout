"""High-level scan orchestration — ARP sweep + register results."""
import socket
import sys
from datetime import datetime

from . import scanner, storage, oui


state: dict = {"running": False, "progress": 0, "status": "idle"}


def _register_self(data: dict, now: str) -> None:
    """Inject the NetScout host itself into the device list."""
    local_ip = scanner.get_local_ip()
    mac = scanner.get_self_mac()
    if not mac:
        return
    mac = mac.lower()
    existing = data["devices"].get(mac, {})
    data["devices"][mac] = {
        "mac": mac,
        "ip": local_ip,
        "subnet": scanner.get_subnet(local_ip),
        "hostname": existing.get("hostname") or socket.gethostname(),
        "vendor": oui.lookup(mac),
        "label": existing.get("label", "NetScout"),
        "vendor_custom": existing.get("vendor_custom", ""),
        "first_seen": existing.get("first_seen", now),
        "last_seen": now,
        "online": True,
        "open_ports": existing.get("open_ports", []),
        "os_guess": existing.get("os_guess", "Linux/Unix"),
        "latency_ms": existing.get("latency_ms", 0.0),
        "ttl": existing.get("ttl"),
        "enriched_at": existing.get("enriched_at", ""),
        "first_seen_online": existing.get("first_seen_online", now),
        "consecutive_online": existing.get("consecutive_online", 0),
        "switch_port": existing.get("switch_port"),
        "wifi": existing.get("wifi"),
        "connection_type": existing.get("connection_type", ""),
        "category": existing.get("category", ""),
    }


def run() -> None:
    """Run a full network scan. Intended for a background thread."""
    global state
    subnets = scanner.get_subnets_to_scan()
    state = {"running": True, "progress": 10,
             "status": f"Sweeping {len(subnets)} subnet(s)…"}

    raw = scanner.scan_all()
    state["progress"] = 60
    state["status"] = f"Found {len(raw)} devices, resolving names…"

    data = storage.load()
    now = datetime.now().isoformat()

    # MAC can appear on multiple subnets (gateways, switches) — disambiguate
    seen_macs, seen_ips = set(), set()
    for item in raw:
        mac = item.get("mac", "unknown").lower()
        ip  = item.get("ip", "")
        subnet = item.get("subnet", "")

        device_key = mac
        if mac in seen_macs:
            device_key = f"ip:{ip}"
        seen_macs.add(mac)
        seen_ips.add(ip)

        existing = data["devices"].get(device_key, data["devices"].get(mac, {}))
        data["devices"][device_key] = {
            "mac": mac,
            "ip": ip,
            "subnet": subnet,
            "hostname": scanner.resolve_hostname(ip) or existing.get("hostname") or "",
            "vendor": oui.lookup(mac),
            "label": existing.get("label", ""),
            "vendor_custom": existing.get("vendor_custom", ""),
            "first_seen": existing.get("first_seen", now),
            "last_seen": now,
            "online": True,
            "open_ports": existing.get("open_ports", []),
            "os_guess": existing.get("os_guess", ""),
            "latency_ms": existing.get("latency_ms"),
            "ttl": existing.get("ttl"),
            "enriched_at": existing.get("enriched_at", ""),
            "first_seen_online": existing.get("first_seen_online", ""),
            "consecutive_online": existing.get("consecutive_online", 0),
            "switch_port": existing.get("switch_port"),
            "wifi": existing.get("wifi"),
            "connection_type": existing.get("connection_type", ""),
            "category": existing.get("category", ""),
        }

    # Mark anything we didn't see this scan as offline
    self_mac = scanner.get_self_mac()
    for _, dev in data["devices"].items():
        if dev.get("ip") not in seen_ips and dev.get("mac") != self_mac:
            dev["online"] = False

    _register_self(data, now)
    data["last_scan"] = now
    storage.save(data)

    state = {"running": False, "progress": 100, "status": "done"}
