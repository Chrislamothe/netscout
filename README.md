# NetScout

> Home lab network scanner with VLAN-aware ARP discovery, switch port mapping, and wireless client tracking.

NetScout is a self-hosted web tool for visualizing every device on your home network. It scans across multiple VLANs, queries managed switches via SNMP to map devices to physical ports, and identifies wireless clients through your APs.

![Screenshot placeholder](docs/screenshot.png)

## Features

- **VLAN-aware ARP scanning** — auto-detects the correct interface per subnet, scans trunked VLANs simultaneously
- **Switch port mapping** — SNMP queries against managed switches identify which port each device is plugged into
- **Wireless client detection** — Aruba AOS10 APs report associated clients with SSID and band info
- **IEEE OUI vendor database** — full lookup against 40,000+ vendors, downloadable from the UI
- **Custom labels and vendor overrides** — name devices, fix wrong vendors, apply across an entire OUI prefix
- **Device categorization** — auto-classifies as Server, Infrastructure, IoT, or Desktop with a color-coded legend
- **Port scanning & OS fingerprinting** — optional enrichment runs in the background
- **Three views** — compact list with expandable details, card grid, sortable table
- **Persistent storage** — single JSON file, no database needed

## Quick start (Docker)

```bash
git clone https://github.com/Chrislamothe/netscout.git
cd netscout
docker compose up -d
```

Open `http://your-docker-host/` and click **Scan Network**.

The container uses host networking so it can see all VLAN sub-interfaces configured on the Docker host. See [VLAN setup](#vlan-setup) below.

## Quick start (Python)

Requires Python 3.10+ and root for ARP scanning.

```bash
pip install -r requirements.txt
sudo python run.py
```

Then open `http://localhost/`.

## VLAN setup

For multi-VLAN scanning you need the host to have a network presence on each VLAN. On Ubuntu with netplan, create `/etc/netplan/99-vlans.yaml`:

```yaml
network:
  version: 2
  vlans:
    eth0.10:
      id: 10
      link: eth0
      addresses: [192.168.10.250/24]
    eth0.20:
      id: 20
      link: eth0
      addresses: [192.168.20.250/24]
```

Apply with `sudo chmod 600 /etc/netplan/99-vlans.yaml && sudo netplan apply`.

Also configure the upstream switch port as a trunk allowing those VLAN tags. Once that's done, NetScout's UI will auto-detect each `eth0.N` sub-interface and use it for ARP scans on the matching subnet.

## SNMP setup

### Aruba switches (ArubaOS-CX)

```
snmp-server vrf default
snmp-server community YOUR_COMMUNITY
```

### Aruba AOS10 APs

SNMP is configured per-AP-group via your wireless controller or Aruba Central. Same community can be reused.

### Configure in the UI

Open the **⚙ settings** panel and add your switches and APs by IP and community string. Use the **Test** buttons to verify reachability before saving.

## Configuration

Environment variables (mostly for Docker):

| Variable | Default | Purpose |
|---|---|---|
| `NETSCOUT_PORT` | `80` | HTTP listen port |
| `NETSCOUT_DATA_DIR` | working dir | Where `devices.json` and `oui.txt` live |
| `NETSCOUT_ARP_TIMEOUT` | `3` | Seconds to wait for ARP responses per subnet |
| `NETSCOUT_EXTRA_SUBNETS` | empty | Comma-separated CIDR list of extra subnets to scan |
| `NETSCOUT_DISABLE_AUTO_SUBNET` | `0` | Set to `1` to only scan `NETSCOUT_EXTRA_SUBNETS` |

Most things can be configured via the settings panel and persist to `devices.json`.

## Why not WatchYourLAN/Pi-hole/Fing/etc?

NetScout is specifically optimized for home labs running managed switches and enterprise APs. It assumes you have SNMP-capable infrastructure and want to map every device to its physical switch port or wireless AP. If you just want presence detection on a flat network, lighter tools may be a better fit.

## Project layout

```
netscout/
├── netscout/
│   ├── app.py            # Flask routes
│   ├── config.py         # constants & env vars
│   ├── storage.py        # devices.json persistence
│   ├── scanner.py        # ARP scanning + interface detection
│   ├── snmp.py           # switch + AP SNMP queries
│   ├── enrichment.py     # port scan, OS fingerprint, latency
│   ├── scan_runner.py    # high-level scan orchestration
│   └── oui.py            # IEEE OUI database
├── templates/index.html
├── static/{app.js,style.css}
├── Dockerfile
├── docker-compose.yml
└── run.py
```

## License

MIT — see [LICENSE](LICENSE).
