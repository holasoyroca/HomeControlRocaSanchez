# 🏠 HomeControlRocaSanchez — Centro de Control Domótico, Cast y Android (Linux)

Herramienta integral en Bash para gestionar desde Linux todos los dispositivos inteligentes del hogar: **Smart TVs con Android TV**, **Móviles y Tablets Android (Xiaomi, Samsung, etc.)**, **Chromecasts**, pantallas **Google Nest Hub** y altavoces **Google Home Mini**.

---

## 📡 1. Mapa de Dispositivos Detectados en Casa

| Nombre en Red | IP Local | Modelo / Tipo | Capacidades Soportadas |
| :--- | :--- | :--- | :--- |
| **Toshiba 65** | `192.168.100.201` | Android TV 11 (`shandao`) | Control total ADB (`5555`), Pantalla en vivo (`scrcpy`), Projectivy Launcher, Cast (`8009`) |
| **Dormitorio principal** | `192.168.100.131` | Google Nest Hub (Pantalla) | Envío de vídeo/YouTube/fotos (`catt`), Megafonía por voz (TTS), Control de volumen |
| **Comedor** | `192.168.100.136` | Google Chromecast | Envío de películas locales, YouTube, música y Megafonía TTS |
| **Altavoz Salón** | `192.168.100.135` | Google Home Mini | Megafonía por voz (TTS en español), envío de música/radio, volumen |
| **Habitación** | `192.168.100.132` | Google Home Mini | Megafonía por voz (TTS en español), envío de música/radio, volumen |
| **Teclast T20** | `192.168.100.239` | Tablet Android (`00:92:fa:20:7c:ff`) | Control por USB o ADB Wi-Fi (`adb tcpip 5555`), Pantalla en vivo (`scrcpy`), Limpieza Spyware |
| **Galaxy Watch 5** | `192.168.100.139` | Reloj Wear OS (`SM-R910`) | Auto-detección mDNS, Esfera en vivo (`scrcpy`), Optimización de batería y animaciones `0.5x` |
| **Galaxy Watch 8 Classic** | `192.168.100.245` | Reloj Wear OS (`SM-L505F`) | Auto-detección mDNS, Esfera en vivo (`scrcpy`), Optimización de batería y animaciones `0.5x` |
| **Móviles / Tablets** | *USB o Wi-Fi* | Android (Xiaomi, Samsung...) | Pantalla en vivo (`scrcpy`), Limpieza de Bloatware (MIUI/HyperOS/OneUI), Capturas, APKs |

---

## 🚀 2. Inicio Rápido

Ejecuta el panel interactivo desde tu terminal Linux:

```bash
cd ~/git_proyects/HomeControlRocaSanchez
./home_control.sh
```

---

## 🛠️ 3. Funciones Principales de `home_control.sh`

### A) 🗣️ Megafonía Inteligente (Hacer hablar a los altavoces) y Multimedia (`catt` + `gTTS`)
Desde el **Menú 2 (`Menú Altavoces, Chromecast, Nest Hub y Megafonía`)** puedes:
1. **Hacer hablar a cualquier habitación (o a toda la casa a la vez)**:
   * Escribes cualquier texto en tu Linux (ej. *"La cena está lista"*), el sistema sintetiza voz natural en español con `gtts-cli` y la reproduce al instante en el altavoz elegido o simultáneamente en **Salón, Habitación, Dormitorio principal y Comedor**.
2. **Enviar vídeos de YouTube o archivos de tu PC a cualquier pantalla**:
   * Envía un enlace de YouTube o cualquier archivo `.mp4`, `.mp3` o foto de tu ordenador directamente a **Toshiba 65**, **Comedor** o **Dormitorio principal (Nest Hub)**.
3. **Controlar el volumen (0-100), pausar o detener** lo que esté sonando en cualquier habitación.

**Comandos directos por terminal (si prefieres no abrir el menú):**
```bash
# Escanear todos los Chromecasts y altavoces de la casa
catt scan

# Enviar un vídeo de YouTube a la TV del Comedor o al Dormitorio principal
catt -d "Comedor" cast "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
catt -d "Dormitorio principal" cast "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

# Enviar una película descargada en tu PC a la TV
catt -d "Toshiba 65" cast ~/Descargas/pelicula.mp4

# Hacer que el altavoz de la Habitación diga una frase
gtts-cli -l es "Hola desde mi Linux" --output /tmp/voz.mp3 && catt -d "Habitación" cast /tmp/voz.mp3
```

---

### B) 📱 Conectar y Limpiar Bloatware en Móviles Android (Xiaomi, Samsung, etc.)
Desde el **Menú 3** puedes conectar cualquier móvil o tablet Android de dos formas:
* **Por Cable USB**: Activa *Opciones de desarrollador -> Depuración por USB* en el móvil y conéctalo al PC.
* **Sin cables (Depuración Inalámbrica en Android 11+)**:
  1. En el móvil entra en *Ajustes -> Opciones de desarrollador -> Depuración inalámbrica*.
  2. Pulsa en **"Vincular dispositivo con código de vinculación"**.
  3. En `./home_control.sh` elige la opción `3` -> `3` e introduce la `IP:PUERTO` y el código de 6 dígitos.

Una vez conectado tu móvil, desde el **Menú 4 (`scrcpy`)** y el **Menú 5 (`Limpiador de Bloatware`)** puedes:
* **Manejar el móvil o tablet en una ventana de tu escritorio Linux** con ratón y teclado (`scrcpy`).
* **Limpiar Spyware y Bloatware de la Tablet Teclast T20 (`192.168.100.239`)**:
  * Neutraliza y desinstala el conocido backdoor/spyware chino **Adups FOTA** (`com.adups.fota` y `com.adups.fota.sysoper`), el rastreador de ubicación de **Baidu** (`com.baidu.map.location`), el teclado chino Pinyin (`com.google.android.inputmethod.pinyin`), `com.example`, `com.mediatek.mtklogger` y Google Play Music (`com.google.android.music`).
* **Limpiar Bloatware de Xiaomi (MIUI / HyperOS)**: Elimina el demonio de publicidad `com.miui.msa.global`, telemetría `com.miui.analytics`, `com.miui.daemon`, navegador promocional, servicios ocultos de Facebook y juegos basura.
* **Limpiar Bloatware de Samsung (OneUI)**: Elimina servicios en segundo plano de Facebook, Bixby innecesario, Samsung Pay Mini, Game Home y OneDrive preinstalado.
* **Restaurar cualquier paquete** en 1 segundo si algún día lo necesitas (`adb shell cmd package install-existing <paquete>`).

---

### C) 📺 Modo Sin Anuncios en Smart TVs (Projectivy Launcher)
Incluye un instalador automático de **Projectivy Launcher** (Opción `5` -> `4`) para cualquier Android TV / Google TV / Fire TV de la casa:
* Libera espacio en `/data` (`pm trim-caches`), descarga la última versión oficial de Projectivy Launcher, desactiva `com.google.android.tvlauncher` y `com.google.android.tvrecommendations`, y asigna el botón **HOME** del mando al nuevo menú limpio sin anuncios.

---

## 📦 4. Herramientas Instaladas en tu Sistema (`~/.local/bin`)
* **`adb` (v37.0.1)**: Android SDK Platform-Tools oficial.
* **`scrcpy` (v5.0.1)**: Espejo y control de pantalla de baja latencia para Android.
* **`catt` (v0.13.3)**: *Cast All The Things* para control de Chromecast, Google Home y Nest Hub.
* **`gtts-cli`**: Sintetizador de voz de Google (*Google Text-to-Speech*) para megafonía doméstica.
* **`gh` (v2.103.3)**: Cliente oficial de GitHub.
