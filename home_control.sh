#!/usr/bin/env bash
# ==============================================================================
#  HOME CONTROL ROCA SÁNCHEZ - Centro de Control Domótico, Cast y ADB (Linux)
#  Gestiona: Smart TVs, Móviles Android, Chromecast, Nest Hub y Google Home
# ==============================================================================

export PATH="$HOME/.local/bin:$PATH"
ADB_TARGET="192.168.100.201:5555"
CAST_TARGET="Toshiba 65"

# Colores
C_RESET='\033[0m'
C_BOLD='\033[1m'
C_CYAN='\033[1;36m'
C_GREEN='\033[1;32m'
C_YELLOW='\033[1;33m'
C_RED='\033[1;31m'

pausa() {
    echo ""
    read -rp "Pulsa ENTER para continuar..." _
}

# ------------------------------------------------------------------------------
# 1. ESCÁNER Y SELECCIÓN DE DISPOSITIVOS
# ------------------------------------------------------------------------------
escanear_dispositivos() {
    echo -e "\n${C_CYAN}🔍 Escaneando dispositivos Google Cast / Nest / Chromecast en tu red...${C_RESET}"
    catt scan
    echo -e "\n${C_CYAN}⌚📱 Dispositivos Android 11+ / Wear OS (Galaxy Watch 5) detectados por mDNS:${C_RESET}"
    adb mdns services
    echo -e "\n${C_CYAN}📡 Comprobando Tablet Teclast T20 y otros equipos en Wi-Fi...${C_RESET}"
    if ping -c 1 -W 1 192.168.100.239 >/dev/null 2>&1; then
        echo -e "${C_GREEN}✔ 192.168.100.239 - Tablet Teclast T20 (MAC 00:92:fa:20:7c:ff - Activa en Wi-Fi)${C_RESET}"
    else
        echo -e "${C_YELLOW}○ 192.168.100.239 - Tablet Teclast T20 (En reposo / pantalla apagada)${C_RESET}"
    fi
    echo -e "\n${C_CYAN}📱 Dispositivos Android (ADB) conectados actualmente:${C_RESET}"
    adb devices -l
}

seleccionar_cast() {
    echo -e "\n${C_CYAN}=== Selecciona el dispositivo Cast / Altavoz / Pantalla ===${C_RESET}"
    echo " 1) Toshiba 65          (192.168.100.201 - Android TV Salón)"
    echo " 2) Comedor             (192.168.100.136 - Chromecast)"
    echo " 3) Dormitorio principal(192.168.100.131 - Google Nest Hub con pantalla)"
    echo " 4) Altavoz Salón       (192.168.100.135 - Google Home Mini)"
    echo " 5) Habitación          (192.168.100.132 - Google Home Mini)"
    echo " 6) Escribir otro nombre o IP manualmente"
    read -rp "Elige dispositivo [1-6]: " c_opt
    case $c_opt in
        1) CAST_TARGET="192.168.100.201" ;;
        2) CAST_TARGET="192.168.100.136" ;;
        3) CAST_TARGET="192.168.100.131" ;;
        4) CAST_TARGET="192.168.100.135" ;;
        5) CAST_TARGET="192.168.100.132" ;;
        6) read -rp "Introduce IP o nombre exacto: " CAST_TARGET ;;
        *) echo "Manteniendo: $CAST_TARGET" ;;
    esac
    echo -e "${C_GREEN}✅ Dispositivo Cast activo: $CAST_TARGET${C_RESET}"
}

seleccionar_adb() {
    echo -e "\n${C_CYAN}=== Conectar / Seleccionar Dispositivo Android (TV, Reloj, Tablet o Móvil) ===${C_RESET}"
    echo " 1) TV Toshiba 65 Salón       (192.168.100.201:5555)"
    echo " 2) Tablet Teclast T20        (192.168.100.239:5555)"
    echo " 3) Reloj Galaxy Watch 5      (SM-R910 en 192.168.100.139 - Auto mDNS)"
    echo " 4) Activar ADB por Wi-Fi en Tablet/Móvil conectado por USB (adb tcpip 5555)"
    echo " 5) Conectar a otra IP manualmente (puerto 5555)"
    echo " 6) Emparejar otro Móvil Android 11+ por Depuración Inalámbrica (Código de 6 dígitos)"
    echo " 7) Usar Tablet/Móvil conectado directamente por cable USB"
    read -rp "Elige opción [1-7]: " a_opt
    case $a_opt in
        1)
            ADB_TARGET="192.168.100.201:5555"
            adb connect "$ADB_TARGET"
            ;;
        2)
            ADB_TARGET="192.168.100.239:5555"
            adb connect "$ADB_TARGET"
            ;;
        3)
            conn_mdns=$(adb mdns services | awk '/_adb-tls-connect._tcp/ {print $3; exit}')
            pair_mdns=$(adb mdns services | awk '/_adb-tls-pairing._tcp/ {print $3; exit}')
            if [ -n "$pair_mdns" ]; then
                echo -e "${C_GREEN}⌚ Detectada pantalla de vinculación del Galaxy Watch 5 en $pair_mdns${C_RESET}"
                read -rp "Introduce el código de 6 dígitos que muestra el reloj: " w_code
                adb pair "$pair_mdns" "$w_code"
                conn_mdns=$(adb mdns services | awk '/_adb-tls-connect._tcp/ {print $3; exit}')
            fi
            if [ -n "$conn_mdns" ]; then
                ADB_TARGET="$conn_mdns"
                if ! adb connect "$ADB_TARGET" | grep -q "connected to"; then
                    echo -e "${C_YELLOW}👉 En el reloj pulsa '+ Vincular dispositivo nuevo' y vuelve a elegir esta opción 3.${C_RESET}"
                fi
            else
                echo -e "${C_YELLOW}⚠️ No se detectó el reloj en mDNS. Asegúrate de tener activada la Depuración Inalámbrica en el Watch 5.${C_RESET}"
            fi
            ;;
        4)
            echo -e "${C_YELLOW}1. Conecta la Teclast T20 (o móvil) por cable USB a este PC.${C_RESET}"
            echo -e "${C_YELLOW}2. Activa 'Opciones de desarrollador -> Depuración por USB' y acepta el aviso en la pantalla.${C_RESET}"
            read -rp "Pulsa ENTER cuando esté conectada por USB..." _
            usb_dev=$(adb devices | awk 'NR>1 && $2=="device" && $1 !~ /:/ {print $1; exit}')
            if [ -n "$usb_dev" ]; then
                adb -s "$usb_dev" tcpip 5555
                sleep 2
                ADB_TARGET="192.168.100.239:5555"
                adb connect "$ADB_TARGET"
                echo -e "${C_GREEN}✅ ¡Listo! Ya puedes desconectar el cable USB y manejarla por Wi-Fi en $ADB_TARGET.${C_RESET}"
            else
                echo -e "${C_RED}❌ No se detectó por USB (o falta aceptar el permiso en la pantalla de la tablet).${C_RESET}"
            fi
            ;;
        5)
            read -rp "Introduce la IP del dispositivo (ej. 192.168.100.140): " ip_dev
            [[ "$ip_dev" != *:* ]] && ip_dev="${ip_dev}:5555"
            ADB_TARGET="$ip_dev"
            adb disconnect "$ADB_TARGET" >/dev/null 2>&1
            adb connect "$ADB_TARGET"
            echo -e "${C_YELLOW}👉 Si es la primera vez, acepta el cartel en la pantalla del dispositivo.${C_RESET}"
            ;;
        6)
            echo -e "${C_YELLOW}En tu móvil/reloj ve a: Ajustes -> Opciones de desarrollador -> Depuración inalámbrica -> Vincular con código${C_RESET}"
            read -rp "Introduce IP:PUERTO de vinculación (ej. 192.168.100.139:39123): " pair_addr
            read -rp "Introduce el código de 6 dígitos: " pair_code
            adb pair "$pair_addr" "$pair_code"
            read -rp "Ahora introduce IP:PUERTO principal de Depuración inalámbrica: " conn_addr
            ADB_TARGET="$conn_addr"
            adb connect "$ADB_TARGET"
            ;;
        7)
            usb_dev=$(adb devices | awk 'NR>1 && $2=="device" && $1 !~ /:/ {print $1; exit}')
            if [ -n "$usb_dev" ]; then
                ADB_TARGET="$usb_dev"
                echo -e "${C_GREEN}✅ Dispositivo por USB seleccionado: $ADB_TARGET${C_RESET}"
            else
                echo -e "${C_RED}❌ No se detectó ningún dispositivo por USB. Conéctalo y activa la Depuración USB.${C_RESET}"
            fi
            ;;
    esac
    adb devices -l
}

# ------------------------------------------------------------------------------
# 2. FUNCIONES DE ALTAVOCES, CHROMECAST Y MEGAFONÍA (TTS)
# ------------------------------------------------------------------------------
hacer_hablar_tts() {
    echo -e "\n${C_CYAN}🗣️  MEGAFONÍA / TEXT-TO-SPEECH EN CASA${C_RESET}"
    echo " 1) Hablar solo por el dispositivo seleccionado ($CAST_TARGET)"
    echo " 2) Hablar por TODOS los altavoces y pantallas de la casa a la vez"
    read -rp "Elige alcance [1-2]: " tts_scope
    read -rp "Escribe la frase que quieres que diga: " frase
    [ -z "$frase" ] && return

    archivo_mp3="/tmp/tts_mensaje.mp3"
    echo "Generando voz en español..."
    gtts-cli -l es "$frase" --output "$archivo_mp3"

    if [ "$tts_scope" = "2" ]; then
        for ip in 192.168.100.135 192.168.100.132 192.168.100.131 192.168.100.136; do
            echo "Enviando mensaje a $ip..."
            catt -d "$ip" cast "$archivo_mp3" >/dev/null 2>&1 &
        done
        wait
        echo -e "${C_GREEN}✅ Mensaje reproducido en toda la casa.${C_RESET}"
    else
        catt -d "$CAST_TARGET" cast "$archivo_mp3"
    fi
}

menu_cast_multimedia() {
    while true; do
        echo -e "\n${C_CYAN}=========================================================${C_RESET}"
        echo -e "   📡 CONTROL CAST / ALTAVOCES / NEST HUB (Activo: ${C_GREEN}$CAST_TARGET${C_RESET})"
        echo -e "${C_CYAN}=========================================================${C_RESET}"
        echo " 1) Cambiar dispositivo Cast objetivo (Salón, Comedor, Dormitorio, Habitación...)"
        echo " 2) 🗣️  Hacer hablar al altavoz/TV (Megafonía Text-to-Speech)"
        echo " 3) ▶️  Enviar vídeo de YouTube o URL web"
        echo " 4) 📁 Enviar archivo local de tu PC (película .mp4, música .mp3, imagen)"
        echo " 5) ⏯️  Pausar / Reanudar reproducción"
        echo " 6) ⏹️  Detener reproducción (Stop)"
        echo " 7) 🔊 Cambiar volumen (0 a 100)"
        echo " 8) ℹ️  Ver qué se está reproduciendo ahora mismo"
        echo " 0) Volver al menú principal"
        read -rp "Elige una opción: " mc
        case $mc in
            1) seleccionar_cast ;;
            2) hacer_hablar_tts ;;
            3)
                read -rp "Pega el enlace de YouTube o URL: " url_media
                [ -n "$url_media" ] && catt -d "$CAST_TARGET" cast "$url_media"
                ;;
            4)
                read -rp "Ruta del archivo en tu Linux (ej. ~/Descargas/video.mp4): " ruta_local
                ruta_local="${ruta_local/#\~/$HOME}"
                if [ -f "$ruta_local" ]; then
                    catt -d "$CAST_TARGET" cast "$ruta_local"
                else
                    echo -e "${C_RED}❌ El archivo no existe: $ruta_local${C_RESET}"
                fi
                ;;
            5) catt -d "$CAST_TARGET" play_toggle ;;
            6) catt -d "$CAST_TARGET" stop ;;
            7)
                read -rp "Introduce nivel de volumen (0-100): " vol
                catt -d "$CAST_TARGET" volume "$vol"
                ;;
            8) catt -d "$CAST_TARGET" status ;;
            0) break ;;
        esac
    done
}

# ------------------------------------------------------------------------------
# 3. LIMPIADOR MULTI-MARCA DE BLOATWARE Y OPTIMIZADOR (ADB)
# ------------------------------------------------------------------------------
menu_bloatware() {
    while true; do
        echo -e "\n${C_CYAN}=========================================================${C_RESET}"
        echo -e "   🧹 LIMPIADOR DE BLOATWARE Y OPTIMIZADOR (Activo: ${C_GREEN}$ADB_TARGET${C_RESET})"
        echo -e "${C_CYAN}=========================================================${C_RESET}"
        echo " 1) Limpiar Bloatware TV Toshiba / Vestel / Android TV (Freeview UK, Telemetría, Demos)"
        echo " 2) Limpiar Spyware/Bloatware Tablet TECLAST T20 (Adups FOTA backdoor, Baidu, Pinyin)"
        echo " 3) Limpiar Bloatware Móvil XIAOMI / REDMI / POCO (Publicidad MSA, Analytics, Basura MIUI/HyperOS)"
        echo " 4) Limpiar Bloatware Móvil SAMSUNG (Facebook preinstalado, Bixby extra, telemetría)"
        echo " 5) Optimizar y limpiar Bloatware Reloj GALAXY WATCH 5 (Global Goals, Bixby, Animaciones 0.5x)"
        echo " 6) Instalar Projectivy Launcher (Sin anuncios) y quitar Launcher de Google en TV"
        echo " 7) Restaurar Launcher original de Google en TV"
        echo " 8) Liberar espacio de almacenamiento y limpiar caché (pm trim-caches + df -h)"
        echo " 9) Buscar / Listar paquetes instalados en el dispositivo"
        echo "10) Desinstalar o Restaurar un paquete manualmente por nombre"
        echo " 0) Volver al menú principal"
        read -rp "Elige una opción: " mb
        case $mb in
            1)
                for pkg in \
                  uk.co.freeview.amc_catchup uk.co.freeview.amc_horror uk.co.freeview.bbc \
                  uk.co.freeview.bbc_sounds uk.co.freeview.ch4_vod uk.co.freeview.ch5 \
                  uk.co.freeview.explore uk.co.freeview.fvpconfigauth uk.co.freeview.itv \
                  uk.co.freeview.mdsclient uk.co.freeview.onnow uk.co.freeview.stv \
                  uk.co.freeview.tifbridge uk.co.freeview.uktv com.mediatek.tv.freeviewplay \
                  com.vestel.vestelreporter fusion.android.tv.demo \
                  android.autoinstalls.config.vestel.medusa com.google.android.feedback \
                  com.google.android.play.games com.google.android.videos; do
                    echo -n "Eliminando $pkg: "
                    adb -s "$ADB_TARGET" shell pm uninstall "$pkg" >/dev/null 2>&1 || true
                    adb -s "$ADB_TARGET" shell pm uninstall -k --user 0 "$pkg"
                done
                ;;
            2)
                echo "Eliminando Spyware (Adups FOTA / Baidu) y Bloatware en Teclast T20..."
                for pkg in \
                  com.adups.fota com.adups.fota.sysoper com.baidu.map.location \
                  com.google.android.inputmethod.pinyin com.google.android.music \
                  com.example com.mediatek.mtklogger com.google.android.feedback \
                  com.android.providers.partnerbookmarks; do
                    echo -n "Desactivando/Eliminando $pkg: "
                    adb -s "$ADB_TARGET" shell pm disable-user --user 0 "$pkg" >/dev/null 2>&1 || true
                    adb -s "$ADB_TARGET" shell pm uninstall -k --user 0 "$pkg"
                done
                ;;
            3)
                echo "Eliminando publicidad y telemetría de Xiaomi (MIUI / HyperOS)..."
                for pkg in \
                  com.miui.msa.global com.miui.analytics com.miui.daemon \
                  com.miui.AdvertisingIdSettings com.xiaomi.mipicks com.miui.CleanMaster \
                  com.xiaomi.glgm com.mi.globalbrowser com.miui.bugreport \
                  com.miui.yellowpage com.facebook.services com.facebook.system \
                  com.facebook.appmanager com.netflix.partner.activation; do
                    echo -n "Eliminando $pkg: "
                    adb -s "$ADB_TARGET" shell pm uninstall -k --user 0 "$pkg"
                done
                ;;
            4)
                echo "Eliminando bloatware preinstalado en Samsung (OneUI)..."
                for pkg in \
                  com.facebook.services com.facebook.system com.facebook.appmanager \
                  com.facebook.katana com.samsung.android.bixby.agent \
                  com.samsung.android.bixby.wakeup com.samsung.android.spaymini \
                  com.samsung.android.game.gamehome com.microsoft.skydrive; do
                    echo -n "Eliminando $pkg: "
                    adb -s "$ADB_TARGET" shell pm uninstall -k --user 0 "$pkg"
                done
                ;;
            5)
                echo "Optimizando Samsung Galaxy Watch 5 (Wear OS) y ahorrando batería..."
                for pkg in \
                  com.samsung.sree \
                  com.samsung.sree.classic \
                  com.samsung.sree.countdown \
                  com.samsung.sree.digital \
                  com.samsung.sree.spin \
                  com.samsung.android.bixby.agent \
                  com.samsung.android.bixby.wakeup \
                  com.microsoft.office.outlook \
                  com.google.android.apps.wearable.retailattractloop \
                  com.sec.android.diagmonagent \
                  com.samsung.android.dqagent; do
                    echo -n "Eliminando $pkg: "
                    adb -s "$ADB_TARGET" shell pm uninstall -k --user 0 "$pkg"
                done
                echo "Acelerando animaciones del reloj a 0.5x..."
                adb -s "$ADB_TARGET" shell settings put global window_animation_scale 0.5
                adb -s "$ADB_TARGET" shell settings put global transition_animation_scale 0.5
                adb -s "$ADB_TARGET" shell settings put global animator_duration_scale 0.5
                adb -s "$ADB_TARGET" shell pm trim-caches 999G
                echo -e "${C_GREEN}✅ Galaxy Watch 5 optimizado y acelerado.${C_RESET}"
                ;;
            6)
                echo "Descargando e instalando Projectivy Launcher oficial..."
                APK_URL=$(curl -s https://api.github.com/repos/spocky/miproja1/releases/latest | grep -o 'https://[^"]*\.apk' | head -n 1)
                curl -sSL "$APK_URL" -o /tmp/ProjectivyLauncher.apk
                adb -s "$ADB_TARGET" shell pm trim-caches 999G
                adb -s "$ADB_TARGET" install -r /tmp/ProjectivyLauncher.apk
                adb -s "$ADB_TARGET" shell pm disable-user --user 0 com.google.android.tvlauncher
                adb -s "$ADB_TARGET" shell pm disable-user --user 0 com.google.android.tvrecommendations
                adb -s "$ADB_TARGET" shell pm disable-user --user 0 com.mediatek.android.leanbacklauncher.partnercustomizer
                adb -s "$ADB_TARGET" shell cmd package set-home-activity com.spocky.projengmenu/.ui.home.MainActivity
                adb -s "$ADB_TARGET" shell input keyevent 3
                echo -e "${C_GREEN}✅ Projectivy Launcher activado sin anuncios.${C_RESET}"
                ;;
            7)
                adb -s "$ADB_TARGET" shell cmd package install-existing com.google.android.tvrecommendations >/dev/null 2>&1
                adb -s "$ADB_TARGET" shell pm enable com.google.android.tvlauncher
                adb -s "$ADB_TARGET" shell pm enable com.google.android.tvrecommendations
                adb -s "$ADB_TARGET" shell pm enable com.mediatek.android.leanbacklauncher.partnercustomizer
                adb -s "$ADB_TARGET" shell input keyevent 3
                echo -e "${C_GREEN}✅ Launcher original restaurado.${C_RESET}"
                ;;
            8)
                adb -s "$ADB_TARGET" shell pm trim-caches 999G
                adb -s "$ADB_TARGET" shell df -h /data
                ;;
            9)
                read -rp "Filtro de búsqueda (deja en blanco para ver todas las de usuario): " filtro
                if [ -z "$filtro" ]; then
                    adb -s "$ADB_TARGET" shell pm list packages -3
                else
                    adb -s "$ADB_TARGET" shell pm list packages | grep -i "$filtro"
                fi
                ;;
            10)
                read -rp "Nombre del paquete: " pkg
                read -rp "¿(d)esinstalar o (r)estaurar '$pkg'? [d/r]: " acc
                if [ "$acc" = "d" ]; then
                    adb -s "$ADB_TARGET" shell pm uninstall -k --user 0 "$pkg"
                elif [ "$acc" = "r" ]; then
                    adb -s "$ADB_TARGET" shell cmd package install-existing "$pkg"
                fi
                ;;
            0) break ;;
        esac
    done
}

# ------------------------------------------------------------------------------
# MENÚ PRINCIPAL
# ------------------------------------------------------------------------------
while true; do
    echo -e "\n${C_BOLD}=================================================================${C_RESET}"
    echo -e " 🏠 ${C_CYAN}HOME CONTROL ROCA SÁNCHEZ${C_RESET} | ADB: ${C_GREEN}$ADB_TARGET${C_RESET} | Cast: ${C_YELLOW}$CAST_TARGET${C_RESET}"
    echo -e "${C_BOLD}=================================================================${C_RESET}"
    echo "  1) 🔍 Escanear todos los dispositivos de la casa (Cast, Nest, TV, ADB)"
    echo "  2) 📡 Menú Altavoces, Chromecast, Nest Hub y Megafonía (Hacer hablar / Cast)"
    echo "  3) 📱 Cambiar dispositivo Android objetivo (TV, Fire TV o Móvil por Wi-Fi/USB)"
    echo "  4) 🖥️  Ver y controlar pantalla en vivo en tu Linux (scrcpy)"
    echo "  5) 🧹 Menú Limpiador de Bloatware (TV, Xiaomi, Samsung) y Projectivy Launcher"
    echo "  6) 🔊 Subir / Bajar / Silenciar volumen (ADB)"
    echo "  7) 🎮 Mando rápido ADB (Home, Atrás, Power, Enviar texto)"
    echo "  8) 📸 Hacer captura de pantalla del dispositivo Android"
    echo "  9) 📦 Instalar un archivo .APK desde tu PC"
    echo " 10) 💻 Abrir consola interna del dispositivo (adb shell)"
    echo "  0) Salir"
    echo "-----------------------------------------------------------------"
    read -rp "Elige una opción: " opcion

    case $opcion in
        1) escanear_dispositivos ; pausa ;;
        2) menu_cast_multimedia ;;
        3) seleccionar_adb ;;
        4) scrcpy -s "$ADB_TARGET" -m 1280 -b 4M ;;
        5) menu_bloatware ;;
        6)
            read -rp "¿(s)ubir, (b)ajar o (m)ute?: " v_opt
            case $v_opt in
                s) adb -s "$ADB_TARGET" shell input keyevent 24 ;;
                b) adb -s "$ADB_TARGET" shell input keyevent 25 ;;
                m) adb -s "$ADB_TARGET" shell input keyevent 164 ;;
            esac
            ;;
        7)
            read -rp "¿(h)ome, (a)trás, (p)ower o (t)exto?: " k_opt
            case $k_opt in
                h) adb -s "$ADB_TARGET" shell input keyevent 3 ;;
                a) adb -s "$ADB_TARGET" shell input keyevent 4 ;;
                p) adb -s "$ADB_TARGET" shell input keyevent 26 ;;
                t)
                    read -rp "Texto a escribir: " txt
                    adb -s "$ADB_TARGET" shell input text "${txt// /%s}"
                    ;;
            esac
            ;;
        8)
            archivo="captura_$(date +%Y%m%d_%H%M%S).png"
            if adb -s "$ADB_TARGET" exec-out screencap -p > "$archivo" && [ -s "$archivo" ]; then
                echo -e "${C_GREEN}✅ Captura guardada en: $archivo${C_RESET}"
            else
                rm -f "$archivo"
                echo -e "${C_RED}❌ Error al capturar pantalla.${C_RESET}"
            fi
            ;;
        9)
            read -rp "Ruta del archivo .apk: " apk_path
            apk_path="${apk_path/#\~/$HOME}"
            adb -s "$ADB_TARGET" install -r "$apk_path"
            ;;
        10) adb -s "$ADB_TARGET" shell ;;
        0) exit 0 ;;
        *) echo "Opción no válida." ;;
    esac
done
