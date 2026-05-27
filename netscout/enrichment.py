"""Per-device enrichment: latency, port scanning, OS fingerprinting.

Run as a background thread via enrichment.run(). State is exposed via the
module-level `state` dict for polling from the UI.
"""
import concurrent.futures
import socket
import subprocess
import sys
from datetime import datetime

from . import config, storage, snmp


# Shared progress state, read by API endpoints
state: dict = {"running": False, "progress": 0, "status": "idle", "total": 0, "done": 0}


def ping_latency(ip: str, count: int = 3) -> float | None:
    """Return average RTT in ms, or None if unreachable."""
    try:
        result = subprocess.run(
            ["ping", "-c", str(count), "-W", "1", "-q", ip],
            capture_output=True, text=True, timeout=10,
        )
        for line in result.stdout.splitlines():
            if "rtt" in line or "round-trip" in line:
                parts = line.split("=")[-1].strip().split("/")
                return round(float(parts[1]), 2)
    except Exception:
        pass
    return None


def scan_ports(ip: str, ports: list, timeout: float = 0.5) -> list:
    """TCP connect scan. Returns list of {port, service} dicts."""
    def check(port):
        s = None
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(timeout)
            if s.connect_ex((ip, port)) == 0:
                return port
        except Exception:
            pass
        finally:
            try:
                if s:
                    s.close()
            except Exception:
                pass
        return None

    open_ports = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=50) as ex:
        for result in ex.map(check, ports):
            if result is not None:
                open_ports.append({
                    "port": result,
                    "service": config.PORT_NAMES.get(result, "unknown"),
                })
    return sorted(open_ports, key=lambda x: x["port"])


def guess_os(ip: str, open_ports: list) -> tuple[str, int | None]:
    """Heuristic OS fingerprint from TTL + open ports."""
    ttl = None
    try:
        result = subprocess.run(
            ["ping", "-c", "1", "-W", "1", ip],
            capture_output=True, text=True, timeout=5,
        )
        for line in result.stdout.splitlines():
            if "ttl=" in line.lower():
                for part in line.split():
                    if part.lower().startswith("ttl="):
                        ttl = int(part.split("=")[1])
                        break
    except Exception:
        pass

    port_nums = {p["port"] for p in open_ports}

    if ttl is None:
        os_hint = "Unknown"
    elif ttl <= 64:
        os_hint = "Linux/Unix"
    elif ttl <= 128:
        os_hint = "Windows"
    else:
        os_hint = "Network Device"

    if 3389 in port_nums or 5985 in port_nums or 5986 in port_nums:
        os_hint = "Windows"
    elif 22 in port_nums and 3389 not in port_nums and ttl and ttl <= 64:
        os_hint = "Linux/Unix"
    if 9100 in port_nums:
        os_hint = "Printer"
    if 5900 in port_nums and 22 not in port_nums:
        os_hint = "VNC Device"
    if 1883 in port_nums or 8883 in port_nums:
        os_hint = "IoT Device"
    if 7547 in port_nums:
        os_hint = "Router/Modem"

    return os_hint, ttl


def enrich_one(ip: str, ports: list) -> dict:
    """Run full enrichment for a single device."""
    latency = ping_latency(ip)
    open_ports = scan_ports(ip, ports)
    os_guess, ttl = guess_os(ip, open_ports)
    return {
        "latency_ms":  latency,
        "open_ports":  open_ports,
        "os_guess":    os_guess,
        "ttl":         ttl,
        "enriched_at": datetime.now().isoformat(),
    }


def _find_key(data: dict, mac: str) -> str | None:
    """Map a MAC address to its storage key (might be 'mac' or 'ip:X.X.X.X')."""
    for k, v in data["devices"].items():
        if v.get("mac") == mac:
            return k
    return None


def run(profile: str = "top20", custom_ports: list | None = None) -> None:
    """Full enrichment pipeline. Intended to run in a background thread."""
    global state

    data = storage.load()
    online = [d for d in data["devices"].values() if d.get("online")]
    total = len(online)

    if total == 0:
        state = {"running": False, "progress": 100,
                 "status": "No online devices", "total": 0, "done": 0}
        return

    ports = config.PORT_PROFILES.get(profile, config.PORT_PROFILES["top20"])
    if profile == "custom" and custom_ports:
        ports = custom_ports
    ports = sorted(set(ports))

    state = {"running": True, "progress": 0,
             "status": "Querying switches and APs…", "total": total, "done": 0}

    # ── Phase A: Switch port discovery ───────────────────────────────────────
    try:
        switch_table = snmp.get_all_switch_ports()
        data = storage.load()
        for mac, info in switch_table.items():
            key = _find_key(data, mac)
            if key:
                data["devices"][key]["switch_port"] = info
                data["devices"][key]["connection_type"] = "wired"
        storage.save(data)
    except Exception as e:
        print(f"[enrich] Switch discovery failed: {e}", file=sys.stderr, flush=True)

    # ── Phase A2: Wireless client discovery (wins over wired) ────────────────
    try:
        state["status"] = "Querying APs for wireless clients…"
        wifi_table = snmp.get_all_wireless_clients()
        data = storage.load()
        for mac, info in wifi_table.items():
            key = _find_key(data, mac)
            if key:
                data["devices"][key]["wifi"] = info
                data["devices"][key]["connection_type"] = "wireless"
                data["devices"][key].pop("switch_port", None)
        storage.save(data)
    except Exception as e:
        print(f"[enrich] Wireless discovery failed: {e}", file=sys.stderr, flush=True)

    # ── Phase B: Port scan + fingerprint each online device ──────────────────
    state["status"] = f"Port scanning {total} devices ({profile}, {len(ports)} ports)…"

    for i, dev in enumerate(online):
        ip = dev.get("ip", "")
        mac = dev.get("mac", "")
        if not ip:
            continue

        state["status"] = f"Scanning {ip} ({i+1}/{total})…"
        state["progress"] = int((i / total) * 100)

        result = enrich_one(ip, ports)

        data = storage.load()
        key = _find_key(data, mac)
        if key:
            data["devices"][key].update(result)
            existing = data["devices"][key]
            if result["latency_ms"] is not None:
                if not existing.get("first_seen_online"):
                    existing["first_seen_online"] = datetime.now().isoformat()
                existing["consecutive_online"] = existing.get("consecutive_online", 0) + 1
            storage.save(data)

        state["done"] = i + 1

    state = {"running": False, "progress": 100,
             "status": f"Enrichment complete — {total} devices scanned",
             "total": total, "done": total}
