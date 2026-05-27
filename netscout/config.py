"""Configuration constants for NetScout.

Paths, defaults, and tuneable values. Override via environment variables
(NETSCOUT_DATA_DIR, NETSCOUT_PORT, etc.) for Docker deployments.
"""
import os
from pathlib import Path

# ── File paths ────────────────────────────────────────────────────────────────
# In Docker, mount a volume at /data for persistence.
DATA_DIR  = Path(os.environ.get("NETSCOUT_DATA_DIR", Path(__file__).parent.parent))
DATA_FILE = DATA_DIR / "devices.json"
OUI_FILE  = DATA_DIR / "oui.txt"

# ── Server ────────────────────────────────────────────────────────────────────
HTTP_HOST = os.environ.get("NETSCOUT_HOST", "0.0.0.0")
HTTP_PORT = int(os.environ.get("NETSCOUT_PORT", "80"))

# ── Scanning ──────────────────────────────────────────────────────────────────
ARP_TIMEOUT      = int(os.environ.get("NETSCOUT_ARP_TIMEOUT", "3"))
DISABLE_AUTO_SUBNET = os.environ.get("NETSCOUT_DISABLE_AUTO_SUBNET", "0") == "1"

# Default extra subnets — comma-separated CIDR strings.
# Better to configure via the UI which persists to devices.json.
EXTRA_SUBNETS = [
    s.strip() for s in os.environ.get("NETSCOUT_EXTRA_SUBNETS", "").split(",")
    if s.strip()
]

# ── Port profiles for enrichment ──────────────────────────────────────────────
DEFAULT_PORT_PROFILE = "top20"

PORT_PROFILES = {
    "top20": [21, 22, 23, 25, 53, 80, 110, 139, 143, 443, 445, 993, 995,
              1723, 3306, 3389, 5900, 8080, 8443, 8888],
    "top100": sorted(set([
        21, 22, 23, 25, 53, 80, 81, 110, 111, 119, 135, 139, 143, 179,
        199, 443, 445, 465, 514, 543, 544, 548, 587, 631, 646, 873,
        990, 993, 995, 1025, 1026, 1027, 1028, 1029, 1110, 1433, 1720,
        1723, 1755, 1900, 2000, 2001, 2049, 2121, 2717, 3000, 3128,
        3306, 3389, 3986, 4899, 5000, 5009, 5051, 5060, 5101, 5190,
        5357, 5432, 5631, 5666, 5800, 5900, 6000, 6001, 6646, 7070,
        8000, 8008, 8009, 8080, 8081, 8443, 8888, 9100, 9999, 10000,
        32768, 49152, 49153, 49154, 49155, 49156, 49157,
    ])),
    "top1000": list(range(1, 1001)),
    "custom": [],
}

# Port number → service name (used for tooltips in UI)
PORT_NAMES = {
    21: "FTP", 22: "SSH", 23: "Telnet", 25: "SMTP", 53: "DNS",
    80: "HTTP", 110: "POP3", 111: "RPC", 119: "NNTP", 135: "MSRPC",
    139: "NetBIOS", 143: "IMAP", 179: "BGP", 199: "SNMP",
    443: "HTTPS", 445: "SMB", 465: "SMTPS", 514: "Syslog",
    548: "AFP", 587: "SMTP", 631: "IPP", 873: "rsync",
    990: "FTPS", 993: "IMAPS", 995: "POP3S", 1433: "MSSQL",
    1720: "H.323", 1723: "PPTP", 1883: "MQTT", 1900: "UPnP",
    2049: "NFS", 2375: "Docker", 2376: "Docker-TLS", 3000: "Dev",
    3306: "MySQL", 3389: "RDP", 3478: "STUN", 4443: "Alt-HTTPS",
    5000: "UPnP", 5060: "SIP", 5432: "PostgreSQL", 5900: "VNC",
    5938: "TeamViewer", 6379: "Redis", 7547: "TR-069",
    8000: "HTTP-Alt", 8008: "HTTP-Alt", 8080: "HTTP-Proxy",
    8443: "HTTPS-Alt", 8883: "MQTT-TLS", 8888: "HTTP-Alt",
    9000: "PHP-FPM", 9090: "Openshift", 9100: "Printer",
    9200: "Elasticsearch", 10000: "Webmin", 27017: "MongoDB",
    32400: "Plex", 49152: "UPnP", 51820: "WireGuard",
}

# ── SNMP defaults ─────────────────────────────────────────────────────────────
# Initial values — UI persists changes to devices.json.
DEFAULT_SWITCHES = []
DEFAULT_APS = []

# Aruba CX / Bridge MIB OIDs
OID_SYS_DESCR     = "1.3.6.1.2.1.1.1.0"
OID_FDB_PORT      = "1.3.6.1.2.1.17.4.3.1.2"
OID_PORT_IFINDEX  = "1.3.6.1.2.1.17.1.4.1.2"
OID_IF_DESCR      = "1.3.6.1.2.1.2.2.1.2"
OID_IF_ALIAS      = "1.3.6.1.2.1.31.1.1.1.18"

# Aruba AOS10 AP MIB OIDs
OID_AP_NAME         = "1.3.6.1.4.1.14823.2.3.3.1.1.2.0"
OID_AP_SSID_INDEX   = "1.3.6.1.4.1.14823.2.3.3.1.1.7.1.1"
OID_AP_SSID_NAME    = "1.3.6.1.4.1.14823.2.3.3.1.1.7.1.2"
OID_CLIENT_MAC      = "1.3.6.1.4.1.14823.2.3.3.1.2.1.1.1"
OID_CLIENT_AP       = "1.3.6.1.4.1.14823.2.3.3.1.2.1.1.2"
OID_CLIENT_SSID_IDX = "1.3.6.1.4.1.14823.2.3.3.1.2.1.1.7"

RADIO_BAND = {
    0: "2.4 GHz", 1: "5 GHz",  2: "5 GHz",  3: "5 GHz",  4: "5 GHz",
    5: "6 GHz",   6: "6 GHz",  7: "6 GHz",  8: "6 GHz",  9: "6 GHz",
}
