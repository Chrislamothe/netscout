"""Flask routes for NetScout.

All business logic lives in scanner/snmp/enrichment/scan_runner modules;
this file just exposes HTTP endpoints and serves the UI.
"""
import re
import threading

from flask import Flask, Response, jsonify, render_template, request

from . import config, storage, oui, scanner, snmp, enrichment, scan_runner

app = Flask(__name__)


# ── UI ────────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


# ── Scan ──────────────────────────────────────────────────────────────────────

@app.route("/api/scan", methods=["POST"])
def api_scan():
    if scan_runner.state["running"]:
        return jsonify({"error": "Scan already running"}), 409
    threading.Thread(target=scan_runner.run, daemon=True).start()
    return jsonify({"ok": True})


@app.route("/api/scan/status")
def api_scan_status():
    return jsonify(scan_runner.state)


@app.route("/api/devices")
def api_devices():
    data = storage.load()

    def ip_sort_key(d):
        ip = d.get("ip", "")
        try:
            octets = [int(o) for o in ip.split(".")]
            if len(octets) != 4:
                return (999, 999, 999, 999)
            # Sort by last octet first (devices grouped by purpose)
            return (octets[3], octets[0], octets[1], octets[2])
        except Exception:
            return (999, 999, 999, 999)

    devices = sorted(data["devices"].values(), key=ip_sort_key)
    return jsonify({"devices": devices, "last_scan": data.get("last_scan")})


# ── Per-device edits ──────────────────────────────────────────────────────────

def _find_key(mac: str) -> tuple[dict, str | None]:
    data = storage.load()
    for k, v in data["devices"].items():
        if v.get("mac") == mac:
            return data, k
    return data, None


@app.route("/api/device/<mac>/label", methods=["PUT"])
def api_set_label(mac):
    data, key = _find_key(mac)
    if not key:
        return jsonify({"error": "Device not found"}), 404
    label = (request.get_json() or {}).get("label", "").strip()
    data["devices"][key]["label"] = label
    storage.save(data)
    return jsonify({"ok": True, "label": label})


@app.route("/api/device/<mac>/vendor", methods=["PUT"])
def api_set_vendor(mac):
    body = request.get_json() or {}
    vendor_custom = body.get("vendor_custom", "").strip()
    apply_all = body.get("apply_all", False)

    data, key = _find_key(mac)
    if not key:
        return jsonify({"error": "Device not found"}), 404

    oui_prefix = mac[:8].lower()
    updated_macs = [mac]
    if apply_all and vendor_custom:
        for m, dev in data["devices"].items():
            if dev.get("mac", "")[:8].lower() == oui_prefix:
                dev["vendor_custom"] = vendor_custom
                if dev.get("mac") not in updated_macs:
                    updated_macs.append(dev.get("mac"))
    else:
        data["devices"][key]["vendor_custom"] = vendor_custom

    oui_matches = sum(
        1 for d in data["devices"].values()
        if d.get("mac", "")[:8].lower() == oui_prefix and d.get("mac") != mac
    )
    storage.save(data)
    return jsonify({
        "ok": True, "vendor_custom": vendor_custom,
        "oui_prefix": oui_prefix, "oui_matches": oui_matches,
        "updated_count": len(updated_macs), "updated_macs": updated_macs,
    })


@app.route("/api/device/<mac>/category", methods=["PUT"])
def api_set_category(mac):
    data, key = _find_key(mac)
    if not key:
        return jsonify({"error": "Device not found"}), 404
    category = (request.get_json() or {}).get("category", "").strip()
    data["devices"][key]["category"] = category
    storage.save(data)
    return jsonify({"ok": True, "category": category})


@app.route("/api/device/<mac>", methods=["DELETE"])
def api_delete_device(mac):
    data, key = _find_key(mac)
    if key:
        data["devices"].pop(key, None)
        storage.save(data)
    return jsonify({"ok": True})


# ── Info / config ─────────────────────────────────────────────────────────────

@app.route("/api/info")
def api_info():
    local_ip = scanner.get_local_ip()
    return jsonify({
        "local_ip": local_ip,
        "subnet": scanner.get_subnet(local_ip),
        "subnets": scanner.get_subnets_to_scan(),
        "extra_subnets": storage.get_extra_subnets(),
        "scapy": scanner.SCAPY_AVAILABLE,
    })


@app.route("/api/subnets", methods=["GET"])
def api_get_subnets():
    return jsonify({
        "subnets": scanner.get_subnets_to_scan(),
        "extra_subnets": storage.get_extra_subnets(),
        "auto_subnet": scanner.get_subnet(scanner.get_local_ip()),
        "disable_auto": config.DISABLE_AUTO_SUBNET,
    })


@app.route("/api/subnets", methods=["POST"])
def api_set_subnets():
    body = request.get_json() or {}
    cidr = re.compile(r"^\d{1,3}(\.\d{1,3}){3}/\d{1,2}$")
    validated = [s.strip() for s in body.get("extra_subnets", [])
                 if isinstance(s, str) and cidr.match(s.strip())]
    storage.set_extra_subnets(validated)
    return jsonify({"ok": True, "extra_subnets": validated})


# ── OUI database ──────────────────────────────────────────────────────────────

@app.route("/api/oui/status")
def api_oui_status():
    return jsonify(oui.status())


@app.route("/api/oui/update", methods=["POST"])
def api_oui_update():
    def _do():
        ok, _ = oui.download()
        if ok:
            data = storage.load()
            for dev in data["devices"].values():
                dev["vendor"] = oui.lookup(dev.get("mac", ""))
            storage.save(data)
    threading.Thread(target=_do, daemon=True).start()
    return jsonify({"ok": True, "message": "Download started"})


@app.route("/api/oui/lookup/<mac>")
def api_oui_lookup(mac):
    return jsonify({"mac": mac, "vendor": oui.lookup(mac)})


# ── Switches & APs (SNMP) ─────────────────────────────────────────────────────

@app.route("/api/switches", methods=["GET"])
def api_get_switches():
    return jsonify({"switches": storage.get_switches()})


@app.route("/api/switches", methods=["POST"])
def api_set_switches():
    body = request.get_json() or {}
    validated = []
    for sw in body.get("switches", []):
        if sw.get("ip") and sw.get("community"):
            validated.append({
                "ip": sw["ip"].strip(),
                "community": sw["community"].strip(),
                "name": (sw.get("name") or sw["ip"]).strip(),
            })
    storage.set_switches(validated)
    return jsonify({"ok": True, "switches": validated})


@app.route("/api/switches/test", methods=["POST"])
def api_test_switch():
    body = request.get_json() or {}
    ok, desc = snmp.test_switch(body.get("ip", ""), body.get("community", ""))
    return jsonify({"ok": ok, "description": desc})


@app.route("/api/switches/poll", methods=["POST"])
def api_poll_switches():
    def _do():
        table = snmp.get_all_switch_ports()
        wifi = snmp.get_all_wireless_clients()
        data = storage.load()
        mac_to_key = {dev["mac"]: k for k, dev in data["devices"].items()}
        for mac, info in table.items():
            key = mac_to_key.get(mac)
            if key and data["devices"][key].get("connection_type") != "wireless":
                data["devices"][key]["switch_port"] = info
                data["devices"][key]["connection_type"] = "wired"
        for mac, info in wifi.items():
            key = mac_to_key.get(mac)
            if key:
                data["devices"][key]["wifi"] = info
                data["devices"][key]["connection_type"] = "wireless"
                data["devices"][key].pop("switch_port", None)
        storage.save(data)
    threading.Thread(target=_do, daemon=True).start()
    return jsonify({"ok": True})


@app.route("/api/aps", methods=["GET"])
def api_get_aps():
    return jsonify({"aps": storage.get_aps()})


@app.route("/api/aps", methods=["POST"])
def api_set_aps():
    body = request.get_json() or {}
    validated = []
    for ap in body.get("aps", []):
        if ap.get("ip") and ap.get("community"):
            validated.append({
                "ip": ap["ip"].strip(),
                "community": ap["community"].strip(),
                "name": (ap.get("name") or ap["ip"]).strip(),
            })
    storage.set_aps(validated)
    return jsonify({"ok": True, "aps": validated})


@app.route("/api/aps/test", methods=["POST"])
def api_test_ap():
    body = request.get_json() or {}
    ok, desc = snmp.test_ap(body.get("ip", ""), body.get("community", ""))
    return jsonify({"ok": ok, "description": desc})


@app.route("/api/aps/poll", methods=["POST"])
def api_poll_aps():
    def _do():
        wifi = snmp.get_all_wireless_clients()
        data = storage.load()
        mac_to_key = {dev["mac"]: k for k, dev in data["devices"].items()}
        for mac, info in wifi.items():
            key = mac_to_key.get(mac)
            if key:
                data["devices"][key]["wifi"] = info
                data["devices"][key]["connection_type"] = "wireless"
                data["devices"][key].pop("switch_port", None)
        storage.save(data)
    threading.Thread(target=_do, daemon=True).start()
    return jsonify({"ok": True})


# ── Enrichment ────────────────────────────────────────────────────────────────

@app.route("/api/enrich", methods=["POST"])
def api_enrich():
    if enrichment.state["running"]:
        return jsonify({"error": "Enrichment already running"}), 409
    body = request.get_json() or {}
    profile = body.get("profile", config.DEFAULT_PORT_PROFILE)
    custom = body.get("custom_ports", [])
    try:
        custom = [int(p) for p in custom]
    except Exception:
        custom = []
    threading.Thread(target=enrichment.run, args=(profile, custom), daemon=True).start()
    return jsonify({"ok": True})


@app.route("/api/enrich/status")
def api_enrich_status():
    return jsonify(enrichment.state)


@app.route("/api/enrich/profiles")
def api_enrich_profiles():
    return jsonify({
        "profiles": {k: len(v) for k, v in config.PORT_PROFILES.items()},
        "default": config.DEFAULT_PORT_PROFILE,
    })


# ── Main entry point ──────────────────────────────────────────────────────────

def main() -> None:
    oui.load()
    print(f"\n  NetScout — http://{config.HTTP_HOST}:{config.HTTP_PORT}\n", flush=True)
    app.run(host=config.HTTP_HOST, port=config.HTTP_PORT, debug=False)


if __name__ == "__main__":
    main()
