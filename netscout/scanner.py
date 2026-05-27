"""Network scanning via scapy ARP broadcasts.

Auto-detects the correct interface for each subnet so scans on VLAN
sub-interfaces (ens34.2, ens34.3, etc.) reach the right segments.
"""
import socket
import subprocess
import sys
import ipaddress

from . import config

try:
    from scapy.all import ARP, Ether, srp
    SCAPY_AVAILABLE = True
except ImportError:
    SCAPY_AVAILABLE = False


def get_local_ip() -> str:
    """Best-effort detection of this machine's primary IP."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "192.168.1.1"


def get_subnet(ip: str) -> str:
    """Derive a /24 subnet string from an IP."""
    parts = ip.split(".")
    return f"{parts[0]}.{parts[1]}.{parts[2]}.0/24"


def get_self_mac() -> str | None:
    """Return the MAC of the interface holding our primary IP."""
    try:
        local_ip = get_local_ip()
        ip_out = subprocess.check_output(["ip", "-o", "-4", "addr", "show"], text=True)
        iface = None
        for line in ip_out.splitlines():
            if local_ip in line:
                iface = line.split()[1]
                break
        if not iface:
            return None
        link_out = subprocess.check_output(["ip", "-o", "link", "show"], text=True)
        for line in link_out.splitlines():
            if line.split()[1].rstrip(":") == iface:
                parts = line.split()
                for i, p in enumerate(parts):
                    if p == "link/ether":
                        return parts[i + 1]
    except Exception:
        pass
    return None


def resolve_hostname(ip: str) -> str | None:
    try:
        return socket.gethostbyaddr(ip)[0]
    except Exception:
        return None


def get_interface_for_subnet(subnet: str) -> str | None:
    """Find the local interface that has an address inside this subnet.

    Critical for VLAN scanning: scapy must send the ARP broadcast out the
    sub-interface that has a layer-2 path to the target VLAN.
    """
    try:
        network = ipaddress.ip_network(subnet, strict=False)
        output = subprocess.check_output(["ip", "-o", "-4", "addr", "show"], text=True)
        for line in output.splitlines():
            parts = line.split()
            if len(parts) < 4:
                continue
            iface = parts[1]
            addr = parts[3].split("/")[0]
            try:
                if ipaddress.ip_address(addr) in network:
                    return iface
            except Exception:
                continue
    except Exception:
        pass
    return None


def get_subnets_to_scan() -> list:
    """Build the full subnet list from auto-detection + saved config."""
    from . import storage  # avoid circular
    subnets = []
    if not config.DISABLE_AUTO_SUBNET:
        subnets.append(get_subnet(get_local_ip()))
    for s in storage.get_extra_subnets():
        s = s.strip()
        if s and s not in subnets:
            subnets.append(s)
    return subnets


def _arp_scan_scapy(subnet: str, iface: str | None = None, timeout: int | None = None) -> list:
    """Run a scapy ARP sweep on a single subnet."""
    if timeout is None:
        timeout = config.ARP_TIMEOUT
    results = []
    pkt = Ether(dst="ff:ff:ff:ff:ff:ff") / ARP(pdst=subnet)
    kwargs = {"timeout": timeout, "verbose": False}
    if iface:
        kwargs["iface"] = iface
    answered, _ = srp(pkt, **kwargs)
    for _, received in answered:
        results.append({
            "ip": received.psrc,
            "mac": received.hwsrc,
            "subnet": subnet,
            "iface": iface or "",
        })
    return results


def _arp_scan_fallback(subnets: list) -> list:
    """Fallback: ping sweep + read system ARP cache. Used when scapy missing."""
    results = []
    for subnet in subnets:
        base = ".".join(subnet.split("/")[0].split(".")[:3])
        procs = []
        for i in range(1, 255):
            ip = f"{base}.{i}"
            p = subprocess.Popen(
                ["ping", "-c", "1", "-W", "1", "-q", ip],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            procs.append(p)
            if len(procs) >= 50:
                for p in procs:
                    p.wait()
                procs = []
        for p in procs:
            p.wait()
    try:
        arp_out = subprocess.check_output(["arp", "-n"], text=True)
        for line in arp_out.splitlines():
            parts = line.split()
            if len(parts) >= 3 and ":" in parts[2] and parts[2] != "(incomplete)":
                results.append({"ip": parts[0], "mac": parts[2], "subnet": ""})
    except Exception:
        pass
    return results


def scan_all() -> list:
    """Scan all configured subnets. Returns list of {ip, mac, subnet, iface}."""
    subnets = get_subnets_to_scan()
    print(f"[scan] Sweeping subnets: {subnets}", file=sys.stderr, flush=True)
    if SCAPY_AVAILABLE:
        out = []
        for subnet in subnets:
            try:
                iface = get_interface_for_subnet(subnet)
                results = _arp_scan_scapy(subnet, iface=iface)
                out.extend(results)
            except Exception as e:
                print(f"[scan] Error on {subnet}: {e}", file=sys.stderr, flush=True)
        if out:
            return out
    return _arp_scan_fallback(subnets)
