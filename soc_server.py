#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SOC ROCA SÁNCHEZ - Servidor de Pantalla Táctica de Ciberseguridad y Domótica
Diseñado a medida para la Tablet Teclast T20 (2560x1600 16:10) y portable a Raspberry Pi.
Persistencia portátil por MAC e IP en: devices_inventory.json
"""

import json
import os
import re
import socket
import subprocess
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

PORT = 8090
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INVENTORY_FILE = os.path.join(BASE_DIR, "devices_inventory.json")

ADB_BIN = os.path.expanduser("~/.local/bin/adb")
if not os.path.exists(ADB_BIN):
    ADB_BIN = "adb"
CATT_BIN = os.path.expanduser("~/.local/bin/catt")
if not os.path.exists(CATT_BIN):
    CATT_BIN = "catt"
GTTS_BIN = os.path.expanduser("~/.local/bin/gtts-cli")
if not os.path.exists(GTTS_BIN):
    GTTS_BIN = "gtts-cli"

INVENTORY_LOCK = threading.Lock()
EVENT_LOGS = []
PREV_ONLINE_IPS = set()
LAST_NET_IO = {"rx": 0, "tx": 0, "ts": time.time()}

# Diccionario de fabricantes OUI (cargado desde nmap + prefijos adicionales conocidos)
OUI_DB = {
    "BC2411": "Proxmox Server Solutions (VM)",
    "880FA2": "Router Fibra / Gateway",
    "0C54A5": "PEGATRON / Sony",
    "BC351E": "Adaptador Wi-Fi Doméstico",
    "0CA64C": "Adaptador Wi-Fi Doméstico",
}


def load_oui_db():
    paths = ["/usr/share/nmap/nmap-mac-prefixes", "/usr/share/ieee-data/oui.txt"]
    for p in paths:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        parts = line.split(None, 1)
                        if len(parts) == 2 and len(parts[0]) == 6:
                            OUI_DB[parts[0].upper()] = parts[1].strip()
                break
            except Exception:
                pass


load_oui_db()


def lookup_mac_vendor(mac):
    if not mac or mac in ("--:--:--:--:--:--", "LOCAL-SERVER"):
        return "Servidor Local / Sin MAC en ARP"
    clean = mac.replace(":", "").replace("-", "").upper()
    if len(clean) < 6:
        return "Desconocido"
    prefix = clean[:6]
    if prefix in OUI_DB:
        return OUI_DB[prefix]
    try:
        first_byte = int(clean[:2], 16)
        if first_byte & 0x02:
            return "MAC Privada / Aleatoria (iOS / Android moderno)"
    except Exception:
        pass
    return "Fabricante OUI Estándar"


def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("192.168.100.1", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "192.168.100.253"


def load_inventory():
    with INVENTORY_LOCK:
        if os.path.exists(INVENTORY_FILE):
            try:
                with open(INVENTORY_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    data.setdefault("by_mac", {})
                    data.setdefault("by_ip", {})
                    return data
            except Exception as e:
                log_event("WARN", f"Error leyendo devices_inventory.json: {e}")
        return {"by_mac": {}, "by_ip": {}}


def save_inventory(data):
    with INVENTORY_LOCK:
        data["updated_at"] = datetime.now().isoformat(timespec="seconds")
        tmp_path = INVENTORY_FILE + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, INVENTORY_FILE)


def log_event(level, msg):
    ts = datetime.now().strftime("%H:%M:%S")
    EVENT_LOGS.insert(0, {"time": ts, "level": level, "msg": msg})
    if len(EVENT_LOGS) > 45:
        EVENT_LOGS.pop()


log_event("INFO", "Sistema SOC Roca Sánchez inicializado con inventario persistente.")


def get_ping_ms(target):
    try:
        out = subprocess.check_output(
            ["ping", "-c", "1", "-W", "1", target],
            stderr=subprocess.DEVNULL,
            universal_newlines=True,
        )
        m = re.search(r"time=([\d.]+)", out)
        return round(float(m.group(1)), 1) if m else -1
    except Exception:
        return -1


def get_host_metrics():
    load1, _, _ = os.getloadavg()
    cpus = os.cpu_count() or 4
    cpu_pct = min(100, round((load1 / cpus) * 100, 1))

    mem_total, mem_avail = 1, 1
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    mem_total = int(line.split()[1])
                elif line.startswith("MemAvailable:"):
                    mem_avail = int(line.split()[1])
    except Exception:
        pass
    ram_pct = round(((mem_total - mem_avail) / mem_total) * 100, 1)
    ram_used_gb = round((mem_total - mem_avail) / (1024 * 1024), 1)
    ram_total_gb = round(mem_total / (1024 * 1024), 1)

    st = os.statvfs("/")
    disk_total = st.f_blocks * st.f_frsize
    disk_free = st.f_bavail * st.f_frsize
    disk_pct = round(((disk_total - disk_free) / disk_total) * 100, 1) if disk_total else 0

    temp_c = 42.0
    try:
        for zone in os.listdir("/sys/class/thermal"):
            if zone.startswith("thermal_zone"):
                with open(f"/sys/class/thermal/{zone}/temp") as tf:
                    val = int(tf.read().strip())
                    if 20000 < val < 110000:
                        temp_c = round(val / 1000.0, 1)
                        break
    except Exception:
        pass

    rx_bytes, tx_bytes = 0, 0
    try:
        with open("/proc/net/dev") as nf:
            for line in nf:
                if ":" in line and "lo:" not in line:
                    parts = line.split(":")[1].split()
                    rx_bytes += int(parts[0])
                    tx_bytes += int(parts[8])
    except Exception:
        pass

    now = time.time()
    dt = max(0.5, now - LAST_NET_IO["ts"])
    rx_kbps = round((rx_bytes - LAST_NET_IO["rx"]) / 1024.0 / dt, 1) if LAST_NET_IO["rx"] else 0.0
    tx_kbps = round((tx_bytes - LAST_NET_IO["tx"]) / 1024.0 / dt, 1) if LAST_NET_IO["tx"] else 0.0
    LAST_NET_IO["rx"] = rx_bytes
    LAST_NET_IO["tx"] = tx_bytes
    LAST_NET_IO["ts"] = now

    return {
        "cpu_pct": cpu_pct,
        "ram_pct": ram_pct,
        "ram_text": f"{ram_used_gb}/{ram_total_gb} GB",
        "disk_pct": disk_pct,
        "temp_c": temp_c,
        "rx_kbps": max(0.0, rx_kbps),
        "tx_kbps": max(0.0, tx_kbps),
        "local_ip": get_local_ip(),
        "hostname": socket.gethostname(),
    }


def get_network_devices():
    global PREV_ONLINE_IPS
    inv = load_inventory()
    by_mac = inv.get("by_mac", {})
    by_ip = inv.get("by_ip", {})

    arp_map = {}
    try:
        out = subprocess.check_output(["ip", "-4", "neigh", "show"], universal_newlines=True)
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 4 and "lladdr" in parts:
                ip = parts[0]
                idx = parts.index("lladdr")
                mac = parts[idx + 1].upper()
                state = parts[-1]
                if state in ("REACHABLE", "DELAY", "STALE", "PERMANENT"):
                    arp_map[ip] = {"mac": mac, "state": state}
    except Exception:
        pass

    local_ip = get_local_ip()
    arp_map[local_ip] = {"mac": "LOCAL-SERVER", "state": "REACHABLE"}

    # Combinar IPs activas en ARP + IPs recordadas de dispositivos en inventario
    known_ips = set(by_ip.keys())
    mac_for_known_ip = {}
    for m, mdata in by_mac.items():
        lip = mdata.get("last_ip")
        if lip:
            known_ips.add(lip)
            mac_for_known_ip[lip] = m

    all_ips = sorted(
        known_ips.union(set(arp_map.keys())),
        key=lambda x: [int(p) if p.isdigit() else 0 for p in x.split(".")],
    )

    devices_list = []
    current_online = set()
    intruders = 0
    inventory_dirty = False

    for ip in all_ips:
        in_arp = ip in arp_map
        arp_state = arp_map[ip]["state"] if in_arp else "OFFLINE"
        mac = arp_map[ip]["mac"] if in_arp else mac_for_known_ip.get(ip, "--:--:--:--:--:--")
        is_online = arp_state in ("REACHABLE", "DELAY", "STALE")

        if is_online:
            current_online.add(ip)

        # 1. Buscar primero por MAC (resiste cambios de IP DHCP y migración a Raspberry Pi)
        entry = None
        if mac and mac not in ("--:--:--:--:--:--", "LOCAL-SERVER") and mac in by_mac:
            entry = by_mac[mac]
            if entry.get("last_ip") != ip and is_online:
                entry["last_ip"] = ip
                inventory_dirty = True
        # 2. Respaldo por IP
        elif ip in by_ip:
            entry = by_ip[ip]
            if mac and mac not in ("--:--:--:--:--:--", "LOCAL-SERVER") and mac not in by_mac:
                by_mac[mac] = {
                    "name": entry.get("name", f"Dispositivo ({ip})"),
                    "icon": entry.get("icon", "📡"),
                    "type": entry.get("type", "Red Local"),
                    "trusted": bool(entry.get("trusted", True)),
                    "last_ip": ip,
                    "notes": entry.get("notes", ""),
                }
                inventory_dirty = True

        vendor = lookup_mac_vendor(mac)

        if entry is not None:
            is_trusted = bool(entry.get("trusted", True))
            if not is_trusted and is_online:
                intruders += 1
            devices_list.append({
                "ip": ip,
                "name": entry.get("name", f"Nodo ({ip})"),
                "icon": entry.get("icon", "📡"),
                "type": entry.get("type", "Red Local"),
                "mac": mac,
                "vendor": vendor,
                "notes": entry.get("notes", ""),
                "online": is_online,
                "state": arp_state,
                "trusted": is_trusted,
                "known": True,
            })
        elif is_online:
            intruders += 1
            devices_list.append({
                "ip": ip,
                "name": f"⚠️ NO RECONOCIDO ({ip})",
                "icon": "🚨",
                "type": "SIN CLASIFICAR",
                "mac": mac,
                "vendor": vendor,
                "notes": "Dispositivo nuevo detectado en la subred. Pulsa para auditar o autorizar.",
                "online": True,
                "state": arp_state,
                "trusted": False,
                "known": False,
            })

    if inventory_dirty:
        save_inventory(inv)

    if PREV_ONLINE_IPS:
        joined = current_online - PREV_ONLINE_IPS
        left = PREV_ONLINE_IPS - current_online
        dev_by_ip = {d["ip"]: d for d in devices_list}
        for ip in joined:
            d = dev_by_ip.get(ip, {})
            nm = d.get("name", ip)
            lvl = "INFO" if d.get("trusted", False) else "ALERT"
            log_event(lvl, f"Conectado: {nm} ({ip} | {d.get('mac', '')})")
        for ip in left:
            d = dev_by_ip.get(ip, {})
            nm = d.get("name", ip)
            log_event("WARN", f"En reposo/desconectado: {nm} ({ip})")
    PREV_ONLINE_IPS = current_online

    return devices_list, len(current_online), intruders


def inspect_device_nmap(ip):
    """Escanea puertos abiertos y servicios de una IP para ayudar al usuario a saber qué es y si es seguro."""
    if not re.match(r"^192\.168\.\d+\.\d+$", ip):
        return {"error": "IP fuera de rango local"}

    ports_found = []
    hostname = ""
    try:
        out = subprocess.check_output(
            ["nmap", "-F", "-T4", "--open", ip],
            stderr=subprocess.DEVNULL,
            universal_newlines=True,
            timeout=12,
        )
        for line in out.splitlines():
            if "Nmap scan report for " in line:
                hostname = line.replace("Nmap scan report for ", "").strip()
            elif "/tcp" in line and "open" in line:
                ports_found.append(line.strip())
    except Exception as e:
        return {"ports": [], "advice": f"No se pudo completar el escaneo de puertos: {e}"}

    # Análisis heurístico de seguridad y tipo de dispositivo
    joined = " ".join(ports_found).lower()
    hints = []
    if "8008/tcp" in joined or "8009/tcp" in joined or "8443/tcp" in joined:
        hints.append("✅ Detectados puertos Google Cast (8008/8009): Es un Google Home, Nest Hub, Chromecast o Android TV legítimo.")
    if "62078/tcp" in joined:
        hints.append("✅ Detectado puerto 62078 (iphone-sync): Es un dispositivo Apple (iPhone o iPad) auténtico.")
    if "5555/tcp" in joined:
        hints.append("🔧 Detectado puerto 5555 (ADB): Es un dispositivo Android/TV con depuración Wi-Fi activa.")
    if "22/tcp" in joined or "8006/tcp" in joined or "5900/tcp" in joined:
        hints.append("🖥️ Detectados servicios de administración (SSH/VNC/Proxmox): Es uno de tus servidores Linux.")
    if "53/tcp" in joined or "80/tcp" in joined and ip.endswith(".1"):
        hints.append("🌐 Es el Router / Puerta de enlace principal de tu red.")
    if not ports_found:
        hints.append(
            "🛡️ Sin puertos TCP abiertos expuestos (0 puertos abiertos). "
            "Comportamiento muy seguro y típico de móviles (iOS/Android), relojes inteligentes o sensores IoT cliente."
        )
    if "23/tcp" in joined or "445/tcp" in joined or "3389/tcp" in joined:
        hints.append("⚠️ Atención: Tiene puertos sensibles abiertos (Telnet/SMB/RDP). Verifica que sea un PC tuyo.")

    return {
        "ip": ip,
        "hostname": hostname or ip,
        "ports": ports_found,
        "hints": hints,
    }


def background_arp_warmer():
    while True:
        try:
            subprocess.run(
                ["nmap", "-sn", "-T4", "192.168.100.0/24"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=12,
            )
        except Exception:
            pass
        time.sleep(25)


HTML_PAGE = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>SOC ROCA SÁNCHEZ // CYBER COMMAND</title>
<style>
  :root {
    --bg: #05080f;
    --panel: #0b1220;
    --border: #1a2c4e;
    --cyan: #00f0ff;
    --green: #00ff88;
    --amber: #ffb800;
    --red: #ff2a55;
    --text: #e2f1ff;
    --muted: #6c86a6;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; user-select: none; }
  body {
    background: var(--bg);
    color: var(--text);
    font-family: 'Segoe UI', Roboto, 'Liberation Sans', monospace;
    height: 100vh;
    overflow: hidden;
    display: flex;
    flex-direction: column;
    padding: 10px;
    gap: 10px;
  }
  header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    background: linear-gradient(90deg, #091326, #0f2140, #091326);
    border: 1px solid var(--cyan);
    box-shadow: 0 0 12px rgba(0, 240, 255, 0.2);
    border-radius: 8px;
    padding: 8px 18px;
  }
  .brand { display: flex; align-items: center; gap: 12px; }
  .brand h1 {
    font-size: 20px;
    letter-spacing: 2px;
    color: var(--cyan);
    text-shadow: 0 0 8px rgba(0,240,255,0.5);
  }
  .status-pill {
    padding: 4px 12px;
    border-radius: 20px;
    font-weight: bold;
    font-size: 13px;
    background: rgba(0, 255, 136, 0.15);
    color: var(--green);
    border: 1px solid var(--green);
  }
  .status-pill.alert {
    background: rgba(255, 42, 85, 0.25);
    color: var(--red);
    border-color: var(--red);
    animation: blink 1s infinite;
  }
  @keyframes blink { 50% { opacity: 0.3; } }
  .clock {
    font-size: 24px;
    font-weight: bold;
    font-family: monospace;
    color: var(--text);
    letter-spacing: 2px;
  }
  .main-grid {
    display: grid;
    grid-template-columns: 300px 1fr 320px;
    gap: 10px;
    flex: 1;
    min-height: 0;
  }
  .panel {
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 12px;
    display: flex;
    flex-direction: column;
    min-height: 0;
  }
  .panel-title {
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 1.4px;
    color: var(--cyan);
    border-bottom: 1px solid var(--border);
    padding-bottom: 6px;
    margin-bottom: 10px;
    display: flex;
    justify-content: space-between;
  }
  .metric-box { margin-bottom: 10px; }
  .metric-header {
    display: flex;
    justify-content: space-between;
    font-size: 13px;
    margin-bottom: 4px;
  }
  .bar-bg {
    width: 100%;
    height: 10px;
    background: #142238;
    border-radius: 5px;
    overflow: hidden;
  }
  .bar-fill {
    height: 100%;
    background: linear-gradient(90deg, var(--cyan), var(--green));
    transition: width 0.4s ease;
  }
  .ping-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
    margin-top: 6px;
    margin-bottom: 10px;
  }
  .stat-card {
    background: #080d18;
    border: 1px solid #162642;
    border-radius: 6px;
    padding: 8px;
    text-align: center;
  }
  .stat-card .val {
    font-size: 19px;
    font-weight: bold;
    color: var(--green);
    font-family: monospace;
  }
  .stat-card .lbl {
    font-size: 11px;
    color: var(--muted);
    margin-top: 2px;
  }
  .devices-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(225px, 1fr));
    gap: 8px;
    overflow-y: auto;
    padding-right: 4px;
  }
  .dev-card {
    background: #080e1a;
    border: 1px solid #162642;
    border-left: 4px solid var(--muted);
    border-radius: 6px;
    padding: 8px 10px;
    display: flex;
    align-items: center;
    gap: 10px;
    cursor: pointer;
    transition: transform 0.12s, border-color 0.15s;
  }
  .dev-card:active { transform: scale(0.97); }
  .dev-card:hover { border-color: var(--cyan); }
  .dev-card.online {
    border-left-color: var(--green);
    background: #0a1526;
  }
  .dev-card.intruder {
    border: 1px solid var(--red);
    border-left: 5px solid var(--red);
    background: rgba(255, 42, 85, 0.15);
    animation: blink 1.2s infinite;
  }
  .dev-icon { font-size: 22px; }
  .dev-info { flex: 1; overflow: hidden; }
  .dev-name { font-size: 13px; font-weight: bold; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .dev-ip { font-size: 12px; color: var(--cyan); font-family: monospace; }
  .dev-meta { font-size: 10px; color: var(--muted); font-family: monospace; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .btn-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
    margin-bottom: 12px;
  }
  .soc-btn {
    background: #10203b;
    color: var(--text);
    border: 1px solid var(--cyan);
    border-radius: 6px;
    padding: 10px 6px;
    font-size: 12px;
    font-weight: bold;
    cursor: pointer;
    text-align: center;
    transition: all 0.15s;
  }
  .soc-btn:active {
    background: var(--cyan);
    color: #000;
    transform: scale(0.97);
  }
  .soc-btn.warn { border-color: var(--amber); color: var(--amber); }
  .soc-btn.danger { border-color: var(--red); color: var(--red); }
  .soc-btn.success { border-color: var(--green); color: var(--green); }
  .log-list {
    flex: 1;
    overflow-y: auto;
    font-family: monospace;
    font-size: 11px;
    background: #050a14;
    border: 1px solid #122038;
    border-radius: 6px;
    padding: 8px;
  }
  .log-item { margin-bottom: 5px; line-height: 1.3; }
  .log-time { color: var(--muted); }
  .log-INFO { color: var(--cyan); }
  .log-WARN { color: var(--amber); }
  .log-ALERT { color: var(--red); font-weight: bold; }

  /* MODAL DE AUDITORÍA Y EDICIÓN DE DISPOSITIVO */
  .modal-backdrop {
    display: none;
    position: fixed;
    inset: 0;
    background: rgba(2, 6, 15, 0.85);
    z-index: 999;
    align-items: center;
    justify-content: center;
    padding: 16px;
  }
  .modal-backdrop.open { display: flex; }
  .modal-card {
    background: #0b1426;
    border: 1px solid var(--cyan);
    box-shadow: 0 0 25px rgba(0, 240, 255, 0.25);
    border-radius: 10px;
    width: 100%;
    max-width: 650px;
    max-height: 92vh;
    overflow-y: auto;
    padding: 18px;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  .modal-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 1px solid var(--border);
    padding-bottom: 8px;
  }
  .modal-header h2 { font-size: 17px; color: var(--cyan); }
  .close-btn {
    background: transparent;
    border: 1px solid var(--muted);
    color: var(--text);
    border-radius: 6px;
    padding: 4px 10px;
    cursor: pointer;
    font-size: 14px;
  }
  .audit-box {
    background: #060b16;
    border: 1px solid #182b49;
    border-radius: 6px;
    padding: 10px;
    font-size: 12px;
    line-height: 1.45;
  }
  .audit-row { display: flex; justify-content: space-between; margin-bottom: 4px; font-family: monospace; }
  .form-row { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  .form-group { display: flex; flex-direction: column; gap: 4px; }
  .form-group label { font-size: 11px; color: var(--cyan); text-transform: uppercase; }
  .form-input {
    background: #060c18;
    border: 1px solid #223b63;
    color: var(--text);
    padding: 8px 10px;
    border-radius: 6px;
    font-size: 13px;
    user-select: text;
  }
  .icon-picker {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-top: 4px;
  }
  .icon-chip {
    background: #081121;
    border: 1px solid #1c3254;
    border-radius: 6px;
    padding: 5px 8px;
    font-size: 16px;
    cursor: pointer;
  }
  .icon-chip.selected {
    border-color: var(--cyan);
    background: rgba(0, 240, 255, 0.2);
  }
  .trust-toggle {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
  }
  .trust-opt {
    padding: 10px;
    border-radius: 6px;
    border: 1px solid #223b63;
    text-align: center;
    cursor: pointer;
    font-weight: bold;
    font-size: 12px;
  }
  .trust-opt.active-safe {
    background: rgba(0, 255, 136, 0.2);
    border-color: var(--green);
    color: var(--green);
  }
  .trust-opt.active-danger {
    background: rgba(255, 42, 85, 0.25);
    border-color: var(--red);
    color: var(--red);
  }
</style>
</head>
<body>
  <header>
    <div class="brand">
      <span style="font-size:26px;">🛡️</span>
      <div>
        <h1>SOC ROCA SÁNCHEZ // RED DOMÉSTICA</h1>
        <div style="font-size:11px; color:var(--muted);" id="node-subtitle">NODO CENTRAL: CARGANDO... &bull; PULSA CUALQUIER NODO PARA AUDITAR O RENOMBRAR</div>
      </div>
    </div>
    <div id="sec-badge" class="status-pill">SISTEMA SEGURO</div>
    <div class="clock" id="clock">--:--:--</div>
  </header>

  <div class="main-grid">
    <!-- COLUMNA IZQUIERDA: TELEMETRÍA Y RED -->
    <div class="panel">
      <div class="panel-title"><span>⚡ TELEMETRÍA NODO CENTRAL</span><span id="host-name">LINUX</span></div>
      <div class="metric-box">
        <div class="metric-header"><span>CPU Carga</span><span id="cpu-val">0%</span></div>
        <div class="bar-bg"><div class="bar-fill" id="cpu-bar" style="width:0%"></div></div>
      </div>
      <div class="metric-box">
        <div class="metric-header"><span>Memoria RAM</span><span id="ram-val">0%</span></div>
        <div class="bar-bg"><div class="bar-fill" id="ram-bar" style="width:0%"></div></div>
      </div>
      <div class="metric-box">
        <div class="metric-header"><span>Almacenamiento Raíz (/)</span><span id="disk-val">0%</span></div>
        <div class="bar-bg"><div class="bar-fill" id="disk-bar" style="width:0%"></div></div>
      </div>

      <div class="ping-grid">
        <div class="stat-card">
          <div class="val" id="temp-val">--°C</div>
          <div class="lbl">TEMP CPU</div>
        </div>
        <div class="stat-card">
          <div class="val" id="online-val">0</div>
          <div class="lbl">HOSTS ACTIVOS</div>
        </div>
        <div class="stat-card">
          <div class="val" id="gw-ping">-- ms</div>
          <div class="lbl">PING ROUTER (.1)</div>
        </div>
        <div class="stat-card">
          <div class="val" id="wan-ping">-- ms</div>
          <div class="lbl">PING INTERNET</div>
        </div>
      </div>

      <div class="panel-title" style="margin-top:6px;"><span>📈 TRÁFICO INTERFAZ LAN</span></div>
      <div class="ping-grid">
        <div class="stat-card">
          <div class="val" id="rx-val" style="color:var(--cyan)">0 KB/s</div>
          <div class="lbl">⬇️ DESCARGA (RX)</div>
        </div>
        <div class="stat-card">
          <div class="val" id="tx-val" style="color:var(--amber)">0 KB/s</div>
          <div class="lbl">⬆️ SUBIDA (TX)</div>
        </div>
      </div>
    </div>

    <!-- COLUMNA CENTRAL: RADAR DE NODOS EN RED -->
    <div class="panel">
      <div class="panel-title">
        <span>📡 RADAR DE NODOS (TOCA UN DISPOSITIVO PARA AUDITAR / RENOMBRAR)</span>
        <span id="scan-status" style="color:var(--green)">● ESCANEO ACTIVO</span>
      </div>
      <div class="devices-grid" id="devices-container"></div>
    </div>

    <!-- COLUMNA DERECHA: MANDOS TÁCTICOS Y LOGS -->
    <div class="panel">
      <div class="panel-title"><span>🎛️ ACCIONES TÁCTICAS (STREAM DECK)</span></div>
      <div class="btn-grid">
        <button class="soc-btn success" onclick="sendAction('ezviz_unlock_1')">🔓 Abrir Telefonillo</button>
        <button class="soc-btn warn" onclick="openEzvizModal()">🔑 Config EZVIZ</button>
        <button class="soc-btn" onclick="sendAction('scan_now')">🔍 Escaneo Nmap</button>
        <button class="soc-btn warn" onclick="sendAction('tts_status')">🗣️ Informe por Voz</button>
        <button class="soc-btn" onclick="sendAction('tv_mute')">🔇 Mute TV Salón</button>
        <button class="soc-btn" onclick="sendAction('tv_home')">🏠 Home TV Salón</button>
        <button class="soc-btn" onclick="sendAction('tv_vol_up')">🔊 Vol+ TV Salón</button>
        <button class="soc-btn" onclick="sendAction('tv_vol_down')">🔉 Vol- TV Salón</button>
        <button class="soc-btn danger" onclick="sendAction('tv_power')">⏻ Power TV Salón</button>
        <button class="soc-btn danger" onclick="sendAction('cast_stop')">⏹️ Parar Altavoces</button>
      </div>

      <div class="panel-title"><span>📜 REGISTRO DE EVENTOS SOC</span></div>
      <div class="log-list" id="log-container"></div>
    </div>
  </div>

  <!-- MODAL DE AUDITORÍA Y GESTIÓN PERSISTENTE -->
  <div class="modal-backdrop" id="dev-modal">
    <div class="modal-card">
      <div class="modal-header">
        <h2 id="m-title">🛡️ FICHA TÁCTICA Y AUDITORÍA DE NODO</h2>
        <button class="close-btn" onclick="closeModal()">✕ Cerrar</button>
      </div>

      <div class="audit-box">
        <div class="audit-row"><span>Dirección IP Actual:</span><strong id="m-ip" style="color:var(--cyan)">--</strong></div>
        <div class="audit-row"><span>Dirección Física (MAC):</span><strong id="m-mac" style="color:var(--amber)">--</strong></div>
        <div class="audit-row"><span>Fabricante Hardware (OUI):</span><strong id="m-vendor" style="color:var(--green)">--</strong></div>
        <div style="margin-top:8px; display:flex; justify-content:space-between; align-items:center; gap:8px;">
          <span style="color:var(--muted); font-size:11px;">¿No sabes qué dispositivo es? Escanea sus puertos para identificarlo:</span>
          <button class="soc-btn" style="padding:6px 12px;" onclick="auditSelectedDevice()" id="btn-audit">🔬 Escaneo Profundo Nmap</button>
        </div>
        <div id="m-audit-results" style="margin-top:8px; display:none; border-top:1px solid #1b3154; padding-top:8px;"></div>
      </div>

      <div class="form-row">
        <div class="form-group">
          <label>Nombre del Dispositivo (Se guarda por MAC e IP)</label>
          <input type="text" class="form-input" id="f-name" placeholder="Ej: iPhone de Rocío / Cámara Salón">
        </div>
        <div class="form-group">
          <label>Categoría / Tipo / Sistema</label>
          <input type="text" class="form-input" id="f-type" placeholder="Ej: Móvil / IoT / Android TV / Servidor">
        </div>
      </div>

      <div class="form-group">
        <label>Icono Identificativo</label>
        <div class="icon-picker" id="icon-picker"></div>
      </div>

      <div class="form-group">
        <label>Notas / Ubicación (Se conserva al migrar a Raspberry Pi)</label>
        <input type="text" class="form-input" id="f-notes" placeholder="Ej: Comprobado el 02/11, enchufe inteligente del dormitorio">
      </div>

      <div class="form-group">
        <label>Estado de Seguridad y Reconocimiento en Casa</label>
        <div class="trust-toggle">
          <div class="trust-opt" id="opt-safe" onclick="setTrust(true)">✅ DISPOSITIVO RECONOCIDO / SEGURO</div>
          <div class="trust-opt" id="opt-danger" onclick="setTrust(false)">🚨 NO RECONOCIDO / INTRUSO (ALERTA)</div>
        </div>
      </div>

      <div style="display:flex; justify-content:flex-end; gap:10px; margin-top:4px;">
        <button class="close-btn" onclick="closeModal()">Cancelar</button>
        <button class="soc-btn success" style="padding:10px 18px;" onclick="saveDevice()">💾 Guardar en devices_inventory.json</button>
      </div>
    </div>
  </div>

  <!-- MODAL DE VINCULACIÓN EZVIZ CLOUD API -->
  <div class="modal-backdrop" id="ezviz-modal">
    <div class="modal-card" style="max-width:520px;">
      <div class="modal-header">
        <h2>🔑 VINCULAR TELEFONILLO EZVIZ (WATCH 8 & SOC)</h2>
        <button class="close-btn" onclick="closeEzvizModal()">✕ Cerrar</button>
      </div>
      <div class="audit-box">
        Conecta tu cuenta de EZVIZ una sola vez. El servidor guardará el token de sesión cifrado localmente en <code>.ezviz_credentials.json</code> para que tanto tu <strong>Galaxy Watch 8 Classic</strong> como esta <strong>Pantalla SOC</strong> abran el telefonillo en 0,5 segundos.
      </div>
      <div class="form-group">
        <label>Usuario EZVIZ (Correo electrónico o Teléfono con +34)</label>
        <input type="text" class="form-input" id="ez-user" placeholder="Ej: tu_correo@gmail.com o +34600000000">
      </div>
      <div class="form-group">
        <label>Contraseña EZVIZ</label>
        <input type="password" class="form-input" id="ez-pass" placeholder="Contraseña de la app EZVIZ">
      </div>
      <div class="form-row">
        <div class="form-group">
          <label>Nº Serie Telefonillo (Opcional, se autodetecta)</label>
          <input type="text" class="form-input" id="ez-serial" placeholder="Autodetectar (ej: K12345678)">
        </div>
        <div class="form-group">
          <label>Código 2FA (Solo si EZVIZ te envía SMS/Email)</label>
          <input type="text" class="form-input" id="ez-2fa" placeholder="Opcional">
        </div>
      </div>
      <div id="ez-status" style="font-size:12px; display:none; padding:8px; border-radius:6px; background:#050b14;"></div>
      <div style="display:flex; justify-content:flex-end; gap:10px; margin-top:4px;">
        <button class="close-btn" onclick="closeEzvizModal()">Cancelar</button>
        <button class="soc-btn success" style="padding:10px 18px;" onclick="saveEzvizConfig()" id="btn-ez-save">🔗 Vincular y Probar Conexión</button>
      </div>
    </div>
  </div>

<script>
  const ICONS = ['📱','📲','💻','🖥️','📺','⌚','🔊','🛏️','📹','🔌','📡','🌐','🛡️','🍎','🎮','🚨'];
  let CURRENT_DEVICES = [];
  let SELECTED_DEV = null;
  let SELECTED_ICON = '📱';
  let SELECTED_TRUST = true;

  function updateClock() {
    const now = new Date();
    document.getElementById('clock').textContent = now.toLocaleTimeString('es-ES', {hour12: false});
  }
  setInterval(updateClock, 1000);
  updateClock();

  function renderIconPicker() {
    const box = document.getElementById('icon-picker');
    box.innerHTML = ICONS.map(ic =>
      `<span class="icon-chip ${ic === SELECTED_ICON ? 'selected' : ''}" onclick="selectIcon('${ic}')">${ic}</span>`
    ).join('');
  }

  function selectIcon(ic) {
    SELECTED_ICON = ic;
    renderIconPicker();
  }

  function setTrust(val) {
    SELECTED_TRUST = val;
    document.getElementById('opt-safe').className = 'trust-opt ' + (val ? 'active-safe' : '');
    document.getElementById('opt-danger').className = 'trust-opt ' + (!val ? 'active-danger' : '');
  }

  function openDeviceModal(ip) {
    const d = CURRENT_DEVICES.find(x => x.ip === ip);
    if (!d) return;
    SELECTED_DEV = d;
    document.getElementById('m-ip').textContent = d.ip + (d.online ? ' (ONLINE)' : ' (STANDBY)');
    document.getElementById('m-mac').textContent = d.mac;
    document.getElementById('m-vendor').textContent = d.vendor || 'Desconocido';
    document.getElementById('f-name').value = d.name.replace(/^⚠️ NO RECONOCIDO \\(.*\\)$/, '');
    document.getElementById('f-type').value = d.type === 'SIN CLASIFICAR' ? (d.vendor || 'Red Local') : d.type;
    document.getElementById('f-notes').value = d.notes || '';
    SELECTED_ICON = d.icon === '🚨' ? '📱' : (d.icon || '📱');
    renderIconPicker();
    setTrust(d.trusted);
    const resBox = document.getElementById('m-audit-results');
    resBox.style.display = 'none';
    resBox.innerHTML = '';
    document.getElementById('dev-modal').classList.add('open');
  }

  function closeModal() {
    document.getElementById('dev-modal').classList.remove('open');
    SELECTED_DEV = null;
  }

  function openEzvizModal() {
    document.getElementById('ez-status').style.display = 'none';
    document.getElementById('ezviz-modal').classList.add('open');
  }

  function closeEzvizModal() {
    document.getElementById('ezviz-modal').classList.remove('open');
  }

  async function saveEzvizConfig() {
    const btn = document.getElementById('btn-ez-save');
    const st = document.getElementById('ez-status');
    btn.textContent = '⏳ Conectando con EZVIZ...';
    st.style.display = 'block';
    st.style.color = 'var(--cyan)';
    st.textContent = 'Autenticando contra ieuopen.ezvizlife.com y buscando tu videoportero...';
    try {
      const r = await fetch('/api/ezviz/config', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          account: document.getElementById('ez-user').value,
          password: document.getElementById('ez-pass').value,
          serial: document.getElementById('ez-serial').value,
          sms_code: document.getElementById('ez-2fa').value
        })
      });
      const res = await r.json();
      if (res.ok) {
        st.style.color = 'var(--green)';
        st.textContent = '✅ ' + res.msg;
        setTimeout(() => { closeEzvizModal(); fetchStatus(); }, 1500);
      } else {
        st.style.color = 'var(--amber)';
        st.textContent = '⚠️ ' + res.msg;
      }
    } catch (e) {
      st.style.color = 'var(--red)';
      st.textContent = '❌ Error de red al configurar EZVIZ.';
    }
    btn.textContent = '🔗 Vincular y Probar Conexión';
  }

  async function auditSelectedDevice() {
    if (!SELECTED_DEV) return;
    const btn = document.getElementById('btn-audit');
    const resBox = document.getElementById('m-audit-results');
    btn.textContent = '⏳ Escaneando puertos...';
    resBox.style.display = 'block';
    resBox.innerHTML = '<div style="color:var(--cyan)">Lanzando sondas Nmap contra ' + SELECTED_DEV.ip + '... (tarda ~4 segundos)</div>';
    try {
      const r = await fetch('/api/inspect?ip=' + encodeURIComponent(SELECTED_DEV.ip));
      const data = await r.json();
      let html = '';
      if (data.ports && data.ports.length > 0) {
        html += '<div style="color:var(--amber); margin-bottom:4px;"><strong>Puertos Abiertos Detectados:</strong></div>';
        html += '<pre style="color:var(--text); background:#030710; padding:6px; border-radius:4px; margin-bottom:6px; font-size:11px;">' + data.ports.join('\\n') + '</pre>';
      } else {
        html += '<div style="color:var(--green); margin-bottom:4px;"><strong>0 puertos TCP abiertos expuestos.</strong></div>';
      }
      if (data.hints && data.hints.length > 0) {
        html += data.hints.map(h => `<div style="margin-top:3px;">${h}</div>`).join('');
      }
      resBox.innerHTML = html;
    } catch (e) {
      resBox.innerHTML = '<div style="color:var(--red)">Error al escanear el nodo.</div>';
    }
    btn.textContent = '🔬 Escaneo Profundo Nmap';
  }

  async function saveDevice() {
    if (!SELECTED_DEV) return;
    const payload = {
      ip: SELECTED_DEV.ip,
      mac: SELECTED_DEV.mac,
      name: document.getElementById('f-name').value.trim() || ('Dispositivo ' + SELECTED_DEV.ip),
      type: document.getElementById('f-type').value.trim() || 'Red Local',
      icon: SELECTED_ICON,
      trusted: SELECTED_TRUST,
      notes: document.getElementById('f-notes').value.trim()
    };
    await fetch('/api/device/save', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload)
    });
    closeModal();
    fetchStatus();
  }

  async function fetchStatus() {
    try {
      const res = await fetch('/api/status');
      const data = await res.json();
      CURRENT_DEVICES = data.devices;

      document.getElementById('node-subtitle').innerHTML =
        `NODO CENTRAL: ${data.host.local_ip} (${data.host.hostname}) &bull; INVENTARIO PORTABLE: devices_inventory.json &bull; TOCA UN NODO PARA AUDITAR/EDITAR`;
      document.getElementById('host-name').textContent = data.host.hostname.toUpperCase();

      document.getElementById('cpu-val').textContent = data.host.cpu_pct + '%';
      document.getElementById('cpu-bar').style.width = data.host.cpu_pct + '%';
      document.getElementById('ram-val').textContent = data.host.ram_text + ' (' + data.host.ram_pct + '%)';
      document.getElementById('ram-bar').style.width = data.host.ram_pct + '%';
      document.getElementById('disk-val').textContent = data.host.disk_pct + '%';
      document.getElementById('disk-bar').style.width = data.host.disk_pct + '%';

      document.getElementById('temp-val').textContent = data.host.temp_c + '°C';
      document.getElementById('online-val').textContent = data.online_count;
      document.getElementById('gw-ping').textContent = data.ping_gw >= 0 ? data.ping_gw + ' ms' : 'ERR';
      document.getElementById('wan-ping').textContent = data.ping_wan >= 0 ? data.ping_wan + ' ms' : 'ERR';
      document.getElementById('rx-val').textContent = data.host.rx_kbps + ' KB/s';
      document.getElementById('tx-val').textContent = data.host.tx_kbps + ' KB/s';

      const badge = document.getElementById('sec-badge');
      if (data.intruders > 0) {
        badge.className = 'status-pill alert';
        badge.textContent = '⚠️ ALERTA: ' + data.intruders + ' NO RECONOCIDO(S)';
      } else {
        badge.className = 'status-pill';
        badge.textContent = '✔ PERÍMETRO SEGURO (' + data.online_count + ' ACTIVOS)';
      }

      const devBox = document.getElementById('devices-container');
      devBox.innerHTML = data.devices.map(d => {
        const cls = !d.trusted ? 'dev-card intruder' : (d.online ? 'dev-card online' : 'dev-card');
        const stColor = d.online ? 'var(--green)' : 'var(--muted)';
        return `<div class="${cls}" onclick="openDeviceModal('${d.ip}')">
          <div class="dev-icon">${d.icon}</div>
          <div class="dev-info">
            <div class="dev-name">${d.name}</div>
            <div class="dev-ip">${d.ip} <span style="color:${stColor}">● ${d.online ? 'ONLINE' : 'STANDBY'}</span></div>
            <div class="dev-meta">${d.type} | ${d.mac}</div>
          </div>
        </div>`;
      }).join('');

      const logBox = document.getElementById('log-container');
      logBox.innerHTML = data.logs.map(l =>
        `<div class="log-item"><span class="log-time">[${l.time}]</span> <span class="log-${l.level}">${l.msg}</span></div>`
      ).join('');
    } catch (e) {}
  }

  async function sendAction(act) {
    document.getElementById('scan-status').textContent = '⚡ EJECUTANDO: ' + act.toUpperCase();
    await fetch('/api/action?cmd=' + act, {method: 'POST'});
    setTimeout(() => {
      document.getElementById('scan-status').textContent = '● ESCANEO ACTIVO';
      fetchStatus();
    }, 800);
  }

  setInterval(fetchStatus, 3500);
  fetchStatus();
</script>
</body>
</html>
"""


class SOCHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/status":
            devices, online_count, intruders = get_network_devices()
            payload = {
                "host": get_host_metrics(),
                "ping_gw": get_ping_ms("192.168.100.1"),
                "ping_wan": get_ping_ms("1.1.1.1"),
                "devices": devices,
                "online_count": online_count,
                "intruders": intruders,
                "logs": EVENT_LOGS,
            }
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        elif parsed.path == "/api/inspect":
            qs = parse_qs(parsed.query)
            ip = qs.get("ip", [""])[0]
            log_event("INFO", f"Auditoría Nmap solicitada sobre el nodo {ip}...")
            res = inspect_device_nmap(ip)
            body = json.dumps(res).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)
        else:
            body = HTML_PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/action":
            qs = parse_qs(parsed.query)
            cmd = qs.get("cmd", [""])[0]
            log_event("INFO", f"Comando táctico recibido: {cmd}")
            threading.Thread(target=self.run_tactical_cmd, args=(cmd,), daemon=True).start()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
        elif parsed.path == "/api/device/save":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8")
            data = json.loads(raw)
            ip = data.get("ip", "").strip()
            mac = data.get("mac", "").strip().upper()
            entry = {
                "name": data.get("name", f"Nodo {ip}"),
                "type": data.get("type", "Red Local"),
                "icon": data.get("icon", "📱"),
                "trusted": bool(data.get("trusted", True)),
                "last_ip": ip,
                "notes": data.get("notes", ""),
            }
            inv = load_inventory()
            if mac and mac not in ("--:--:--:--:--:--", "LOCAL-SERVER"):
                inv["by_mac"][mac] = entry
            if ip:
                inv["by_ip"][ip] = entry
            save_inventory(inv)
            estado_txt = "CONFIABLE" if entry["trusted"] else "INTRUSO / NO RECONOCIDO"
            log_event("INFO" if entry["trusted"] else "ALERT", f"Inventario actualizado: {entry['name']} ({ip} | {mac}) -> {estado_txt}")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
        elif parsed.path == "/api/ezviz/config":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8")
            data = json.loads(raw)
            ez_script = os.path.join(BASE_DIR, "ezviz_unlock.py")
            try:
                out = subprocess.check_output(
                    [
                        "/home/froca/.local/opt/cast-env/bin/python3",
                        ez_script,
                        "config",
                        data.get("account", ""),
                        data.get("password", ""),
                        data.get("serial", ""),
                        data.get("sms_code", ""),
                    ],
                    universal_newlines=True,
                    timeout=18,
                )
                res = json.loads(out.strip().splitlines()[-1])
            except Exception as e:
                res = {"ok": False, "msg": f"Fallo al autenticar con EZVIZ: {e}"}
            log_event("INFO" if res.get("ok") else "WARN", f"EZVIZ Config: {res.get('msg')}")
            body = json.dumps(res).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)

    def run_tactical_cmd(self, cmd):
        tv = "192.168.100.201:5555"
        try:
            if cmd in ("ezviz_unlock_1", "ezviz_unlock_2"):
                lock_no = "2" if cmd.endswith("2") else "1"
                ez_script = os.path.join(BASE_DIR, "ezviz_unlock.py")
                proc = subprocess.run(
                    ["/home/froca/.local/opt/cast-env/bin/python3", ez_script, "unlock", lock_no],
                    capture_output=True,
                    text=True,
                    timeout=12,
                )
                try:
                    res = json.loads(proc.stdout.strip().splitlines()[-1])
                except Exception:
                    res = {"ok": False, "msg": proc.stderr or proc.stdout or "Error desconocido"}
                if res.get("ok"):
                    log_event("INFO", f"🔓 TELEFONILLO EZVIZ ABIERTO: {res.get('msg')}")
                else:
                    log_event("ALERT", f"⚠️ No se pudo abrir EZVIZ: {res.get('msg')}")
            elif cmd == "scan_now":
                subprocess.run(["nmap", "-sn", "-T4", "192.168.100.0/24"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                log_event("INFO", "Barrido Nmap de subred 192.168.100.0/24 completado.")
            elif cmd == "tv_mute":
                subprocess.run([ADB_BIN, "-s", tv, "shell", "input", "keyevent", "164"])
            elif cmd == "tv_home":
                subprocess.run([ADB_BIN, "-s", tv, "shell", "input", "keyevent", "3"])
            elif cmd == "tv_vol_up":
                subprocess.run([ADB_BIN, "-s", tv, "shell", "input", "keyevent", "24"])
            elif cmd == "tv_vol_down":
                subprocess.run([ADB_BIN, "-s", tv, "shell", "input", "keyevent", "25"])
            elif cmd == "tv_power":
                subprocess.run([ADB_BIN, "-s", tv, "shell", "input", "keyevent", "26"])
            elif cmd == "cast_stop":
                for ip in ("192.168.100.135", "192.168.100.132", "192.168.100.131", "192.168.100.136"):
                    subprocess.run([CATT_BIN, "-d", ip, "stop"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            elif cmd == "tts_status":
                _, count, intr = get_network_devices()
                msg = f"Informe del centro de seguridad. Hay {count} dispositivos activos en la red y {intr} no reconocidos."
                subprocess.run([GTTS_BIN, "-l", "es", msg, "--output", "/tmp/soc_tts.mp3"])
                subprocess.run([CATT_BIN, "-d", "192.168.100.135", "cast", "/tmp/soc_tts.mp3"])
        except Exception as e:
            log_event("WARN", f"Error en comando {cmd}: {e}")


if __name__ == "__main__":
    t = threading.Thread(target=background_arp_warmer, daemon=True)
    t.start()
    server = ThreadingHTTPServer(("0.0.0.0", PORT), SOCHandler)
    print(f"🛡️ SOC Server escuchando en http://{get_local_ip()}:{PORT}")
    server.serve_forever()
