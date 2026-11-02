#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SOC ROCA SÁNCHEZ - Servidor de Pantalla Táctica de Ciberseguridad y Domótica
Diseñado a medida para la Tablet Teclast T20 (2560x1600 16:10) desde Linux Mint.
"""

import json
import os
import re
import subprocess
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

PORT = 8090
ADB_BIN = os.path.expanduser("~/.local/bin/adb")
CATT_BIN = os.path.expanduser("~/.local/bin/catt")
GTTS_BIN = os.path.expanduser("~/.local/bin/gtts-cli")

# Inventario oficial de dispositivos autorizados en casa
KNOWN_DEVICES = {
    "192.168.100.1":   {"name": "Router / Gateway",        "icon": "🌐", "type": "Infraestructura", "trusted": True},
    "192.168.100.11":  {"name": "Servidor Linux / VNC",    "icon": "🖥️", "type": "Servidor",        "trusted": True},
    "192.168.100.27":  {"name": "Nodo Servidor (.27)",     "icon": "🖧",  "type": "Servidor",        "trusted": True},
    "192.168.100.100": {"name": "Equipo Red (.100)",       "icon": "💻", "type": "Host Local",      "trusted": True},
    "192.168.100.129": {"name": "Dispositivo IoT (.129)",  "icon": "🔌", "type": "IoT",             "trusted": True},
    "192.168.100.130": {"name": "Dispositivo Espressif",   "icon": "🔌", "type": "IoT",             "trusted": True},
    "192.168.100.131": {"name": "Nest Hub Dormitorio",     "icon": "🛏️", "type": "Fuchsia OS",      "trusted": True},
    "192.168.100.132": {"name": "Google Home Habitación",  "icon": "🔊", "type": "Cast OS",         "trusted": True},
    "192.168.100.133": {"name": "Dispositivo Casa (.133)", "icon": "📡", "type": "Wi-Fi",           "trusted": True},
    "192.168.100.134": {"name": "Cámara / IoT Hualai",     "icon": "📹", "type": "IoT",             "trusted": True},
    "192.168.100.135": {"name": "Altavoz Salón",           "icon": "🔊", "type": "Cast OS",         "trusted": True},
    "192.168.100.136": {"name": "Chromecast Comedor",      "icon": "📺", "type": "Cast OS",         "trusted": True},
    "192.168.100.137": {"name": "Dispositivo Casa (.137)", "icon": "📱", "type": "Wi-Fi",           "trusted": True},
    "192.168.100.138": {"name": "Galaxy S23 Ultra",        "icon": "📱", "type": "One UI / ADB",    "trusted": True},
    "192.168.100.139": {"name": "Galaxy Watch 5 (44mm)",   "icon": "⌚", "type": "Wear OS",         "trusted": True},
    "192.168.100.140": {"name": "Dispositivo Móvil (.140)","icon": "📱", "type": "Wi-Fi",           "trusted": True},
    "192.168.100.142": {"name": "Galaxy Tab S9",           "icon": "平板", "type": "One UI / ADB",  "trusted": True},
    "192.168.100.163": {"name": "Dispositivo AzureWave",   "icon": "📡", "type": "IoT",             "trusted": True},
    "192.168.100.201": {"name": "TV Toshiba 65 Salón",     "icon": "📺", "type": "Android TV 11",   "trusted": True},
    "192.168.100.238": {"name": "Dispositivo Casa (.238)", "icon": "📡", "type": "Wi-Fi",           "trusted": True},
    "192.168.100.239": {"name": "Consola SOC Teclast T20", "icon": "🛡️", "type": "SOC Display",     "trusted": True},
    "192.168.100.245": {"name": "Galaxy Watch 8 Classic",  "icon": "⌚", "type": "Wear OS",         "trusted": True},
    "192.168.100.247": {"name": "Dispositivo Casa (.247)", "icon": "📡", "type": "Wi-Fi",           "trusted": True},
    "192.168.100.249": {"name": "Equipo MSI (.249)",       "icon": "🎮", "type": "PC / Host",       "trusted": True},
    "192.168.100.250": {"name": "Nodo Central froca-mint", "icon": "💻", "type": "SOC Server",      "trusted": True},
}

EVENT_LOGS = []
PREV_ONLINE_IPS = set()
LAST_NET_IO = {"rx": 0, "tx": 0, "ts": time.time()}


def log_event(level, msg):
    ts = datetime.now().strftime("%H:%M:%S")
    EVENT_LOGS.insert(0, {"time": ts, "level": level, "msg": msg})
    if len(EVENT_LOGS) > 40:
        EVENT_LOGS.pop()


log_event("INFO", "Sistema SOC Roca Sánchez inicializado en puerto 8090.")


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
    # CPU Load
    load1, _, _ = os.getloadavg()
    cpus = os.cpu_count() or 4
    cpu_pct = min(100, round((load1 / cpus) * 100, 1))

    # RAM
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

    # Disk
    st = os.statvfs("/")
    disk_total = st.f_blocks * st.f_frsize
    disk_free = st.f_bavail * st.f_frsize
    disk_pct = round(((disk_total - disk_free) / disk_total) * 100, 1) if disk_total else 0

    # Temp
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

    # Network KB/s
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
    }


def get_network_devices():
    global PREV_ONLINE_IPS
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

    arp_map["192.168.100.250"] = {"mac": "LOCAL-SERVER", "state": "REACHABLE"}

    devices_list = []
    current_online = set()
    intruders = 0

    all_ips = sorted(
        set(list(KNOWN_DEVICES.keys()) + list(arp_map.keys())),
        key=lambda x: [int(p) if p.isdigit() else 0 for p in x.split(".")],
    )

    for ip in all_ips:
        in_arp = ip in arp_map
        arp_state = arp_map[ip]["state"] if in_arp else "OFFLINE"
        mac = arp_map[ip]["mac"] if in_arp else "--:--:--:--:--:--"
        is_online = arp_state in ("REACHABLE", "DELAY", "STALE")

        if is_online:
            current_online.add(ip)

        if ip in KNOWN_DEVICES:
            info = KNOWN_DEVICES[ip]
            icon = "📱" if info["icon"] == "平板" else info["icon"]
            devices_list.append({
                "ip": ip,
                "name": info["name"],
                "icon": icon,
                "type": info["type"],
                "mac": mac,
                "online": is_online,
                "state": arp_state,
                "trusted": True,
            })
        elif is_online:
            intruders += 1
            devices_list.append({
                "ip": ip,
                "name": f"⚠️ INTRUSO DETECTADO ({ip})",
                "icon": "🚨",
                "type": "NO AUTORIZADO",
                "mac": mac,
                "online": True,
                "state": arp_state,
                "trusted": False,
            })

    if PREV_ONLINE_IPS:
        joined = current_online - PREV_ONLINE_IPS
        left = PREV_ONLINE_IPS - current_online
        for ip in joined:
            nm = KNOWN_DEVICES.get(ip, {}).get("name", f"IP Desconocida {ip}")
            lvl = "INFO" if ip in KNOWN_DEVICES else "ALERT"
            log_event(lvl, f"Activo en red: {nm} ({ip})")
        for ip in left:
            nm = KNOWN_DEVICES.get(ip, {}).get("name", ip)
            log_event("WARN", f"Pasó a reposo/desconectado: {nm} ({ip})")
    PREV_ONLINE_IPS = current_online

    return devices_list, len(current_online), intruders


def background_arp_warmer():
    """Realiza barridos ligeros cada 25 segundos para mantener viva la tabla ARP."""
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
  .brand {
    display: flex;
    align-items: center;
    gap: 12px;
  }
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
    grid-template-columns: 310px 1fr 330px;
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
    font-size: 13px;
    text-transform: uppercase;
    letter-spacing: 1.5px;
    color: var(--cyan);
    border-bottom: 1px solid var(--border);
    padding-bottom: 6px;
    margin-bottom: 10px;
    display: flex;
    justify-content: space-between;
  }
  .metric-box {
    margin-bottom: 10px;
  }
  .metric-header {
    display: flex;
    justify-content: space-between;
    font-size: 13px;
    margin-bottom: 4px;
  }
  .bar-bg {
    width: 100%;
    height: 10px;
    background: #131f33;
    border-radius: 5px;
    overflow: hidden;
  }
  .bar-fill {
    height: 100%;
    background: linear-gradient(90deg, var(--cyan), var(--green));
    transition: width 0.5s ease;
  }
  .ping-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
    margin-top: 6px;
    margin-bottom: 10px;
  }
  .stat-card {
    background: #070d19;
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 8px;
    text-align: center;
  }
  .stat-card .val {
    font-size: 20px;
    font-weight: bold;
    color: var(--green);
    font-family: monospace;
  }
  .stat-card .lbl {
    font-size: 11px;
    color: var(--muted);
  }
  .devices-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(210px, 1fr));
    gap: 8px;
    overflow-y: auto;
    padding-right: 4px;
  }
  .dev-card {
    background: #08101f;
    border: 1px solid #162642;
    border-left: 4px solid var(--muted);
    border-radius: 6px;
    padding: 8px 10px;
    display: flex;
    align-items: center;
    gap: 10px;
  }
  .dev-card.online {
    border-left-color: var(--green);
    background: linear-gradient(90deg, rgba(0,255,136,0.07), #08101f);
  }
  .dev-card.intruder {
    border-color: var(--red);
    border-left-width: 6px;
    background: rgba(255,42,85,0.18);
    animation: blink 1s infinite;
  }
  .dev-icon { font-size: 24px; }
  .dev-info { flex: 1; overflow: hidden; }
  .dev-name { font-size: 13px; font-weight: bold; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .dev-ip { font-size: 12px; color: var(--cyan); font-family: monospace; }
  .dev-meta { font-size: 10px; color: var(--muted); font-family: monospace; }
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
</style>
</head>
<body>
  <header>
    <div class="brand">
      <span style="font-size:26px;">🛡️</span>
      <div>
        <h1>SOC ROCA SÁNCHEZ // RED DOMÉSTICA</h1>
        <div style="font-size:11px; color:var(--muted);">NODO CENTRAL: 192.168.100.250 (froca-mint) &bull; DISPLAY: TECLAST T20</div>
      </div>
    </div>
    <div id="sec-badge" class="status-pill">SISTEMA SEGURO</div>
    <div class="clock" id="clock">--:--:--</div>
  </header>

  <div class="main-grid">
    <!-- COLUMNA IZQUIERDA: TELEMETRÍA Y RED -->
    <div class="panel">
      <div class="panel-title"><span>⚡ TELEMETRÍA NODO CENTRAL</span><span>LINUX MINT</span></div>
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
        <span>📡 RADAR DE NODOS EN SUBRED 192.168.100.0/24</span>
        <span id="scan-status" style="color:var(--green)">● ESCANEO ACTIVO</span>
      </div>
      <div class="devices-grid" id="devices-container"></div>
    </div>

    <!-- COLUMNA DERECHA: MANDOS TÁCTICOS Y LOGS -->
    <div class="panel">
      <div class="panel-title"><span>🎛️ ACCIONES TÁCTICAS (STREAM DECK)</span></div>
      <div class="btn-grid">
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

<script>
  function updateClock() {
    const now = new Date();
    document.getElementById('clock').textContent = now.toLocaleTimeString('es-ES', {hour12: false});
  }
  setInterval(updateClock, 1000);
  updateClock();

  async function fetchStatus() {
    try {
      const res = await fetch('/api/status');
      const data = await res.json();

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
        badge.textContent = '⚠️ ALERTA: ' + data.intruders + ' INTRUSO(S)';
      } else {
        badge.className = 'status-pill';
        badge.textContent = '✔ PERÍMETRO SEGURO (' + data.online_count + ' ACTIVOS)';
      }

      const devBox = document.getElementById('devices-container');
      devBox.innerHTML = data.devices.map(d => {
        const cls = !d.trusted ? 'dev-card intruder' : (d.online ? 'dev-card online' : 'dev-card');
        const stColor = d.online ? 'var(--green)' : 'var(--muted)';
        return `<div class="${cls}">
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
            log_event("INFO", f"Comando táctico recibido desde Teclast T20: {cmd}")
            threading.Thread(target=self.run_tactical_cmd, args=(cmd,), daemon=True).start()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok":true}')

    def run_tactical_cmd(self, cmd):
        tv = "192.168.100.201:5555"
        try:
            if cmd == "scan_now":
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
                msg = f"Informe del centro de seguridad. Hay {count} dispositivos activos en la red y {intr} intrusos."
                subprocess.run([GTTS_BIN, "-l", "es", msg, "--output", "/tmp/soc_tts.mp3"])
                subprocess.run([CATT_BIN, "-d", "192.168.100.135", "cast", "/tmp/soc_tts.mp3"])
        except Exception as e:
            log_event("WARN", f"Error en comando {cmd}: {e}")


if __name__ == "__main__":
    t = threading.Thread(target=background_arp_warmer, daemon=True)
    t.start()
    server = ThreadingHTTPServer(("0.0.0.0", PORT), SOCHandler)
    print(f"🛡️ SOC Server escuchando en http://192.168.100.250:{PORT}")
    server.serve_forever()
