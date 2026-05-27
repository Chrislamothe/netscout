"""SNMP queries against switches and Aruba AOS10 APs.

Switches: walks the Bridge MIB (dot1dTpFdbPort) to map MACs to switch ports.
APs: walks the Aruba 14823 MIB to identify wireless clients by SSID.
"""
import subprocess
import sys

from . import config


# ── Low-level SNMP wrappers ───────────────────────────────────────────────────

def snmpwalk(ip: str, community: str, oid: str, timeout: int = 10) -> list:
    """Return list of (full_oid_string, value) tuples from net-snmp."""
    try:
        result = subprocess.run(
            ["snmpwalk", "-v2c", "-c", community, "-Oqn", ip, oid],
            capture_output=True, text=True, timeout=timeout,
        )
        rows = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split(None, 1)
            if len(parts) == 2:
                rows.append((parts[0], parts[1].strip().strip('"')))
        return rows
    except Exception as e:
        print(f"[snmp] snmpwalk {ip} {oid}: {e}", file=sys.stderr, flush=True)
        return []


def snmpget(ip: str, community: str, oid: str, timeout: int = 5) -> str | None:
    try:
        result = subprocess.run(
            ["snmpget", "-v2c", "-c", community, "-Oqv", ip, oid],
            capture_output=True, text=True, timeout=timeout,
        )
        return result.stdout.strip().strip('"')
    except Exception:
        return None


def oid_suffix(full_oid: str, base_oid: str) -> str | None:
    """Strip a known base OID prefix, returning the remaining suffix."""
    full = full_oid.lstrip(".")
    base = base_oid.lstrip(".")
    if full.startswith("iso."):
        full = "1." + full[4:]
    if full.startswith(base + "."):
        return full[len(base) + 1:]
    return None


def mac_from_oid_suffix(suffix: str) -> str | None:
    """Convert the last 6 decimal octets of an OID suffix to a MAC."""
    try:
        parts = suffix.split(".")
        octets = parts[-6:]
        if len(octets) < 6:
            return None
        return ":".join(f"{int(o):02x}" for o in octets)
    except Exception:
        return None


def parse_hex_mac(hex_str: str) -> str | None:
    """Parse 'Hex-STRING: 48 00 20 C9 B8 8D' to '48:00:20:c9:b8:8d'."""
    hex_str = hex_str.replace("Hex-STRING:", "").strip()
    octets = hex_str.split()
    if len(octets) == 6:
        return ":".join(o.lower() for o in octets)
    return None


# ── Switch MAC → port discovery ───────────────────────────────────────────────

def get_switch_port_table(switch: dict) -> dict:
    """Query one switch and return {mac: port_info_dict}."""
    ip, community = switch["ip"], switch["community"]
    name = switch.get("name", ip)
    result = {}

    print(f"[snmp] Querying {name} ({ip}) for MAC table…",
          file=sys.stderr, flush=True)

    # 1. bridge port → ifIndex
    port_to_ifindex = {}
    for full_oid, val in snmpwalk(ip, community, config.OID_PORT_IFINDEX):
        suffix = oid_suffix(full_oid, config.OID_PORT_IFINDEX)
        if suffix is None:
            continue
        try:
            port_to_ifindex[int(suffix.split(".")[-1])] = int(val)
        except Exception:
            continue

    # 2. ifIndex → name
    ifindex_to_name = {}
    for full_oid, val in snmpwalk(ip, community, config.OID_IF_DESCR):
        suffix = oid_suffix(full_oid, config.OID_IF_DESCR)
        if suffix is None:
            continue
        try:
            ifindex_to_name[int(suffix)] = val
        except Exception:
            continue

    # 3. ifIndex → alias (port description, optional)
    ifindex_to_alias = {}
    for full_oid, val in snmpwalk(ip, community, config.OID_IF_ALIAS):
        suffix = oid_suffix(full_oid, config.OID_IF_ALIAS)
        if suffix is None:
            continue
        try:
            if val and val != '""':
                ifindex_to_alias[int(suffix)] = val
        except Exception:
            continue

    # 4. MAC → bridge port
    count = 0
    for full_oid, val in snmpwalk(ip, community, config.OID_FDB_PORT):
        suffix = oid_suffix(full_oid, config.OID_FDB_PORT)
        if suffix is None:
            continue
        mac = mac_from_oid_suffix(suffix)
        if not mac:
            continue
        try:
            bridge_port = int(val)
        except Exception:
            continue
        if bridge_port == 0:
            continue

        ifindex = port_to_ifindex.get(bridge_port)
        port_name = ifindex_to_name.get(ifindex, f"port{bridge_port}") if ifindex else f"port{bridge_port}"
        port_alias = ifindex_to_alias.get(ifindex, "") if ifindex else ""

        result[mac] = {
            "switch":    name,
            "switch_ip": ip,
            "port":      port_name,
            "port_desc": port_alias,
            "port_num":  bridge_port,
            "ifindex":   ifindex,
        }
        count += 1

    print(f"[snmp] {name}: {count} MAC→port entries", file=sys.stderr, flush=True)
    return result


def get_all_switch_ports() -> dict:
    """Query every configured switch and merge results."""
    from . import storage
    merged = {}
    for sw in storage.get_switches():
        try:
            merged.update(get_switch_port_table(sw))
        except Exception as e:
            print(f"[snmp] Error querying {sw.get('ip')}: {e}",
                  file=sys.stderr, flush=True)
    return merged


def test_switch(ip: str, community: str) -> tuple[bool, str]:
    """Quick reachability check — returns sysDescr if SNMP responds."""
    val = snmpget(ip, community, config.OID_SYS_DESCR, timeout=5)
    if val:
        return True, val
    return False, "No response — check IP, community, SNMP allow list"


# ── Aruba AP wireless client discovery ────────────────────────────────────────

def get_ap_wireless_clients(ap: dict) -> dict:
    """Query one Aruba AOS10 AP and return {mac: wifi_info_dict}."""
    ip, community = ap["ip"], ap["community"]
    name = ap.get("name", ip)
    result = {}

    print(f"[wifi] Querying {name} ({ip})…", file=sys.stderr, flush=True)

    # SSID index → name
    ssid_map = {}
    for full_oid, val in snmpwalk(ip, community, config.OID_AP_SSID_NAME):
        suffix = oid_suffix(full_oid, config.OID_AP_SSID_NAME)
        if suffix:
            parts = suffix.split(".")
            if len(parts) >= 2:
                try:
                    ssid_map[int(parts[1])] = val
                except Exception:
                    pass

    # Per-client tables
    client_macs = {}
    for full_oid, val in snmpwalk(ip, community, config.OID_CLIENT_MAC):
        suffix = oid_suffix(full_oid, config.OID_CLIENT_MAC)
        if suffix is None:
            continue
        mac = parse_hex_mac(val)
        if mac:
            client_macs[suffix] = mac

    client_ap = {}
    for full_oid, val in snmpwalk(ip, community, config.OID_CLIENT_AP):
        suffix = oid_suffix(full_oid, config.OID_CLIENT_AP)
        if suffix:
            client_ap[suffix] = val

    client_radio = {}
    for full_oid, val in snmpwalk(ip, community, config.OID_CLIENT_SSID_IDX):
        suffix = oid_suffix(full_oid, config.OID_CLIENT_SSID_IDX)
        if suffix:
            try:
                client_radio[suffix] = int(val)
            except Exception:
                pass

    for suffix, mac in client_macs.items():
        radio_idx = client_radio.get(suffix, -1)
        result[mac] = {
            "ap":              client_ap.get(suffix, name),
            "ap_ip":           ip,
            "ssid":            ssid_map.get(radio_idx, "Unknown"),
            "band":            config.RADIO_BAND.get(radio_idx, "WiFi"),
            "connection_type": "wireless",
        }

    print(f"[wifi] {name}: {len(result)} wireless clients",
          file=sys.stderr, flush=True)
    return result


def get_all_wireless_clients() -> dict:
    """Query every configured AP and merge results."""
    from . import storage
    merged = {}
    for ap in storage.get_aps():
        try:
            merged.update(get_ap_wireless_clients(ap))
        except Exception as e:
            print(f"[wifi] Error querying {ap.get('ip')}: {e}",
                  file=sys.stderr, flush=True)
    return merged


def test_ap(ip: str, community: str) -> tuple[bool, str]:
    """Quick reachability check for an AP."""
    val = snmpget(ip, community, config.OID_AP_NAME, timeout=5)
    if val:
        return True, f"AP: {val}"
    return False, "No response — check IP, community, SNMP config"
