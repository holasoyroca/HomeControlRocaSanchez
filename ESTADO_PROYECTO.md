# 📋 Estado Actual del Proyecto — HomeControlRocaSanchez

**Última actualización:** 2 de Noviembre de 2026

## 1. Arquitectura General Desplegada

El ecosistema **HomeControlRocaSanchez** cuenta actualmente con **doble nodo SOC (Alta Disponibilidad)**, control multimedia DLNA/ADB, integración de apertura de telefonillo EZVIZ y contramedidas Wi-Fi sobre el router ASUS RT-AX52 Pro:

| Nodo / Servicio | IP / URL | Función Principal |
| :--- | :--- | :--- |
| **PC Central (Linux Mint - SOC Master)** | `http://192.168.100.253:8090` *(IP dinámica, MAC `C8:5E:A9:46:79:7C`)* | Servidor principal [`soc_server.py`](./soc_server.py), escáner Nmap bajo demanda, edición de inventario, control EZVIZ y expulsión Wi-Fi por SSH. |
| **Router ASUS RT-AX52 Pro (SOC 24/7)** | `http://192.168.100.241:8090` *(MAC `B6:FC:E7:97:45:40`)* | Servidor SOC autónomo embebido en memoria flash NAND (`/jffs/soc`), AdGuard DNS (`dnsmasq`), tuning de Kernel 5.4 (`aarch64`) y bloqueo MAC/Deauth. |
| **Pantalla Dedicada SOC (Teclast T20)** | `192.168.100.139:5555` (ADB Wi-Fi) | Tablet Android en modo Kiosco 24/7 mostrando el panel SOC a pantalla completa. |
| **Samsung Galaxy S23 Ultra** | `192.168.100.138` | Smartphone principal con MIFARE Classic Tool (`de.syss.MifareClassicTool`) instalado para clonado de llaveros NFC CUID Gen2 (Bloque 0 regrabable). |
| **Samsung Galaxy Watch 8 Classic** | `192.168.100.245` | Reloj Wear OS con el APK nativo [`EzvizWatchKey.apk`](./EzvizWatchKey.apk) instalado (Emulación HCE de los AIDs propietarios de EZVIZ + botón de apertura en 1 toque). |
| **Smart TVs (Salón y Dormitorio)** | `192.168.100.168` (LG webOS) / `192.168.100.166` (Samsung Tizen) | Integradas en [`home_control.sh`](./home_control.sh) mediante `cast-cli` (DLNA/UPnP). |

---

## 2. Componentes Clave del Repositorio

* **[`soc_server.py`](./soc_server.py)**: Servidor SOC táctico multi-hilo en puerto `8090`.
  * Auto-detecta la IP local del host al arrancar (`get_local_ip()`).
  * Carga y guarda el inventario persistente en [`devices_inventory.json`](./devices_inventory.json) indexado tanto por **MAC (`by_mac`)** como por **IP (`by_ip`)**.
  * **Ficha Táctica y Auditoría de Nodo**: Al hacer clic en cualquier tarjeta del panel, permite identificar el fabricante (OUI), lanzar un escaneo Nmap de puertos abiertos (`/api/inspect`), editar nombre/icono/confianza (`/api/device/save`) o expulsar/bloquear la MAC en el router ASUS (`/api/asus/kick`).
  * **Integración EZVIZ**: Botones `🔓 Abrir Telefonillo` (`/api/ezviz/unlock`) y `🔑 Config EZVIZ` (`/api/ezviz/config`).
* **[`devices_inventory.json`](./devices_inventory.json)**: Base de datos portable de los dispositivos de la red (`192.168.100.0/24`).
* **[`ezviz_unlock.py`](./ezviz_unlock.py)**: Utilidad CLI y módulo de integración con la nube europea de EZVIZ (`apiieu.ezvizlife.com`) usando el entorno virtual `/home/froca/.local/opt/cast-env/bin/python3` (`pyezvizapi`).
* **[`EzvizWatchKey.apk`](./EzvizWatchKey.apk)** (y código fuente en [`wear_ezviz_nfc/`](./wear_ezviz_nfc)): Aplicación nativa Wear OS que emula por HCE los AIDs de EZVIZ (`F0657A76697A01`, `F0657A76697A02`, `A000000333888888888888`) y envía peticiones de apertura al servidor SOC.
* **[`home_control.sh`](./home_control.sh)**: Menú interactivo maestro para controlar TVs, la pantalla SOC Teclast T20 y el servidor SOC.

---

## 3. Configuración Interna del Router ASUS RT-AX52 Pro (`192.168.100.241`)

* **Acceso SSH**: Habilitado en puerto `22` con clave pública `ed25519` inyectada en NVRAM (`ssh admin@192.168.100.241`).
* **Script de Optimización y Watchdog (`/jffs/scripts/optimize_asus.sh`)**:
  * Ejecutado automáticamente cada 5 minutos mediante `cru` (`AsusOpt`).
  * Aplica mejoras de pila TCP (`tcp_fastopen=3`, `tcp_tw_reuse=1`) y libera caché de RAM (`drop_caches`).
  * Configura **AdGuard DNS (`94.140.14.14` / `94.140.15.15`)** y bloqueo de dominios de anuncios/telemetría en `/etc/dnsmasq.conf`.
  * Mantiene activo el servidor web autónomo `/jffs/busybox httpd -p 8090 -h /jffs/soc`.
* **Servidor SOC Autónomo (`/jffs/soc/`)**:
  * `/jffs/soc/index.html`: Interfaz gráfica del panel SOC.
  * `/jffs/soc/cgi-bin/status`: Script CGI en `awk` que lee `/proc/net/arp`, `/proc/loadavg`, `/proc/meminfo` y cruza las MACs/IPs con `/jffs/soc/inventory.tsv`.

---

## 4. Pendientes / Próximos Pasos Opcionales para Futuras Sesiones

1. **Clonado Físico NFC CUID Gen2 (13.56 MHz)**:
   * Cuando lleguen las pegatinas **Mifare Classic 1K CUID Gen2 (Bloque 0 regrabable)**, usar **MIFARE Classic Tool** en el Galaxy S23 Ultra para leer el Bloque 0 del llavero original EZVIZ y volcarlo en la pegatina para llevarla en la correa del Galaxy Watch 8 Classic.
2. **Cuenta EZVIZ (Opcional si se usa apertura por Nube)**:
   * Si el alta en EZVIZ se hizo mediante *Iniciar sesión con Google*, establecer contraseña propia desde la app móvil de EZVIZ (*Perfil -> Seguridad de la cuenta -> Cambiar contraseña*) para poder usar la apertura remota desde el botón `🔓 Abrir Telefonillo` del panel SOC.
