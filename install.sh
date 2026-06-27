#!/bin/bash
# ============================================================
#  moOde-radio-plus — Install Script
#  Target: moOde Audio Player 10.2.x on Raspberry Pi 4
#  Repo:   https://github.com/frantale70-lgtm/moOde-radio-plus
# ============================================================

set -e

REPO_RAW="https://raw.githubusercontent.com/frantale70-lgtm/moOde-radio-plus/main"
INSTALL_DIR="/opt/moOde_Radio_Cover"
SNIPPET_FILE="moode_sse_snippet.js"
JS_DIR="/var/www/js"
LIB_MIN="/var/www/js/lib.min.js"
HEADER_PHP="/var/www/header.php"
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

# — PULIZIA lib.min.js (migrazione da Arch A) ——
echo "[5/7] Installazione snippet JS e iniezione in header.php..."

if grep -q "moode-sse-patch" "$LIB_MIN" 2>/dev/null; then
    echo "  Snippet Arch A trovato in lib.min.js — rimozione in corso..."
    CLEAN_LINE=$(grep -n "moode-sse-patch" "$LIB_MIN" | head -1 | cut -d: -f1)
    sudo head -n $((CLEAN_LINE - 1)) "$LIB_MIN" | sudo tee /tmp/lib.min.clean > /dev/null
    sudo cp /tmp/lib.min.clean "$LIB_MIN"
    sudo rm -f /tmp/lib.min.clean
    echo "  lib.min.js ripulito."
fi

# Backup lib.min.js pulito — originale solo la prima volta + timestampato
if [ ! -f "${LIB_MIN}.bak.original" ]; then
    sudo cp "$LIB_MIN" "${LIB_MIN}.bak.original"
    echo "  Backup originale lib.min.js creato."
fi
sudo cp "$LIB_MIN" "${LIB_MIN}.bak.$(date +%Y%m%d_%H%M%S)"

# Download snippet standalone in /var/www/js/
curl -fsSL "$REPO_RAW/plugin/$SNIPPET_FILE" \
    | sudo tee "$JS_DIR/$SNIPPET_FILE" > /dev/null
sudo chown root:www-data "$JS_DIR/$SNIPPET_FILE"
sudo chmod 644 "$JS_DIR/$SNIPPET_FILE"
echo "  Snippet scaricato in $JS_DIR/$SNIPPET_FILE"

# Backup header.php — originale solo la prima volta + timestampato
if [ ! -f "${HEADER_PHP}.bak.original" ]; then
    sudo cp "$HEADER_PHP" "${HEADER_PHP}.bak.original"
    echo "  Backup originale header.php creato."
fi
sudo cp "$HEADER_PHP" "${HEADER_PHP}.bak.$(date +%Y%m%d_%H%M%S)"

# Iniezione tag <script> via Python — guard idempotente
sudo python3 - << PYEOF
import re, time, sys

target = '$HEADER_PHP'
snippet = '$SNIPPET_FILE'
tag = '<script src="js/{}?v={}" defer></script>'.format(snippet, int(time.time()))

with open(target, 'r') as f:
    content = f.read()

if snippet in content:
    content = re.sub(
        r'<script src="js/' + re.escape(snippet) + r'\?v=\d+" defer></script>',
        tag,
        content
    )
    print("  Tag già presente — timestamp aggiornato.")
else:
    if '</head>' not in content:
        print("ERRORE: tag </head> non trovato in header.php")
        sys.exit(1)
    content = content.replace('</head>', '    ' + tag + '\n</head>')
    print("  Tag <script> iniettato in header.php.")

with open(target, 'w') as f:
    f.write(content)
PYEOF

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
