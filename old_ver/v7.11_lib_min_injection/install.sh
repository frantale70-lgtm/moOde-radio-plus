#!/bin/bash
# ============================================================
#  moOde-radio-plus — Install Script
#  Target: moOde Audio Player 10.2.x on Raspberry Pi 4
#  Repo:   https://github.com/frantale70-lgtm/moOde-radio-plus
# ============================================================

set -e

REPO_RAW="https://raw.githubusercontent.com/frantale70-lgtm/moOde-radio-plus/main"
INSTALL_DIR="/opt/moOde_Radio_Cover"
SNIPPET_FILE="moode_sse_snippet_v7.11.js"
LIB_MIN="/var/www/js/lib.min.js"
SERVICE_FILE="/etc/systemd/system/moode-sse.service"
LOG_FILE="/var/log/radio-cover.log"
LOGOS_DIR="/var/local/www/imagesw/radio-logos"
NGINX_SITE="/etc/nginx/sites-available/moode-http.conf"

echo ""
echo "============================================="
echo "  moOde-radio-plus — Installazione"
echo "============================================="
echo ""

# — PREREQUISITO ————————————————————————————————
echo "[1/7] Prerequisito moOde..."
echo "  Assicurati che in moOde:"
echo "  Preferences → Cover Art → Radio track covers = No"
read -p "  Confermato? [s/N] " confirm
[[ "$confirm" =~ ^[Ss]$ ]] || { echo "Installazione annullata."; exit 1; }

# — CARTELLE ————————————————————————————————————
echo "[2/7] Creazione cartelle..."
sudo mkdir -p "$INSTALL_DIR"
sudo mkdir -p "$LOGOS_DIR"
sudo touch "$LOG_FILE"

# — PERMESSI ————————————————————————————————————
echo "[3/7] Assegnazione permessi..."
CURRENT_USER=$(whoami)
CURRENT_GROUP=$(id -gn)
sudo chown "$CURRENT_USER":"$CURRENT_GROUP" "$INSTALL_DIR"
sudo chmod 755 "$INSTALL_DIR"
sudo chown root:www-data "$LOG_FILE"
sudo chmod 664 "$LOG_FILE"
sudo chown root:www-data "$LOGOS_DIR"
sudo chmod 755 "$LOGOS_DIR"

# — DOWNLOAD FILE ———————————————————————————————
echo "[4/7] Download file dal repository..."

# Daemon
curl -fsSL "$REPO_RAW/plugin/moode_sse_server.py" \
    -o "$INSTALL_DIR/moode_sse_server.py"
chmod 755 "$INSTALL_DIR/moode_sse_server.py"

# Config — preservato se già esistente (mantiene le API keys)
if [ -f "$INSTALL_DIR/moode_sse_server.config" ]; then
    echo "  Config già presente con API keys — mantenuto invariato."
else
    curl -fsSL "$REPO_RAW/plugin/moode_sse_server.config" \
        -o "$INSTALL_DIR/moode_sse_server.config"
    chmod 755 "$INSTALL_DIR/moode_sse_server.config"
    echo "  Config scaricato. Ricordati di inserire le API keys al termine."
fi

# — INIEZIONE SNIPPET IN lib.min.js ————————————
echo "[5/7] Iniezione snippet in lib.min.js..."

# Verifica esistenza lib.min.js
if [ ! -f "$LIB_MIN" ]; then
    echo "  ERRORE: $LIB_MIN non trovato. Installazione annullata."
    exit 1
fi

# Guard anti-doppia-iniezione
if grep -q "moode-sse-patch V7.11" "$LIB_MIN"; then
    echo "  Snippet V7.11 già presente in lib.min.js — skip."
else
    # Backup originale (solo la prima volta)
    if [ ! -f "${LIB_MIN}.bak.original" ]; then
        sudo cp "$LIB_MIN" "${LIB_MIN}.bak.original"
        echo "  Backup originale lib.min.js creato."
    fi
    # Backup timestampato
    sudo cp "$LIB_MIN" "${LIB_MIN}.bak.$(date +%Y%m%d_%H%M%S)"

    # Download snippet in dir temporanea
    SNIPPET_TMP=$(mktemp)
    curl -fsSL "$REPO_RAW/plugin/$SNIPPET_FILE" -o "$SNIPPET_TMP"

    # Append in coda a lib.min.js
    echo "" | sudo tee -a "$LIB_MIN" > /dev/null
    sudo cat "$SNIPPET_TMP" | sudo tee -a "$LIB_MIN" > /dev/null
    rm -f "$SNIPPET_TMP"

    echo "  Snippet V7.11 iniettato in $LIB_MIN."
fi

# — NGINX PROXY SSE ————————————————————————————
echo "[6/7] Configurazione Nginx proxy SSE..."
if grep -q "cover-events" "$NGINX_SITE" 2>/dev/null; then
    echo "  Nginx già configurato per /cover-events — skip."
else
    sudo cp "$NGINX_SITE" "${NGINX_SITE}.bk.$(date +%Y%m%d_%H%M%S)"
    sudo sed -i 's|include moode-locations.conf;|location /cover-events {\n\t\tproxy_pass http://127.0.0.1:5000;\n\t\tproxy_http_version 1.1;\n\t\tproxy_set_header Connection "";\n\t\tproxy_buffering off;\n\t}\n\tinclude moode-locations.conf;|' "$NGINX_SITE"
    if sudo nginx -t 2>/dev/null; then
        sudo nginx -s reload
        echo "  Nginx configurato e riavviato."
    else
        echo "  ERRORE: test Nginx fallito. Ripristino backup..."
        sudo cp "${NGINX_SITE}.bk."* "$NGINX_SITE" 2>/dev/null || true
        sudo nginx -s reload
        exit 1
    fi
fi

# — SERVIZIO SYSTEMD ————————————————————————————
echo "[7/7] Installazione servizio systemd..."
sudo curl -fsSL "$REPO_RAW/plugin/moode-sse.service" \
    -o "$SERVICE_FILE"
sudo chown root:root "$SERVICE_FILE"
sudo chmod 644 "$SERVICE_FILE"
sudo systemctl daemon-reload
sudo systemctl enable moode-sse.service
sudo systemctl restart moode-sse.service

# — VERIFICA ————————————————————————————————————
sleep 2
if systemctl is-active --quiet moode-sse.service; then
    echo ""
    echo "  moode-sse attivo e in esecuzione."
else
    echo ""
    echo "  Servizio non avviato. Controlla il log:"
    echo "     tail -f $LOG_FILE"
    exit 1
fi

echo ""
echo "============================================="
echo "  Installazione completata."
echo ""
echo "  IMPORTANTE: Inserisci le API keys in:"
echo "    $INSTALL_DIR/moode_sse_server.config"
echo ""
echo "  Poi riavvia il daemon:"
echo "    sudo systemctl restart moode-sse"
echo ""
echo "  Svuota cache kiosk:"
echo "    rm -rf /home/$CURRENT_USER/.cache/chromium"
echo "    sudo systemctl restart localdisplay.service"
echo "============================================="
