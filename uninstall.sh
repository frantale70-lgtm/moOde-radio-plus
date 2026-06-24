#!/bin/bash
# ============================================================
#  moOde-radio-plus — Uninstall Script
#  Target: moOde Audio Player 10.2.x on Raspberry Pi 4
#  Repo:   https://github.com/frantale70-lgtm/moOde-radio-plus
# ============================================================

set -e

INSTALL_DIR="/opt/moOde_Radio_Cover"
JS_FILE="moode_radio_plus_snippet.js"
JS_DEST="/var/www/js/$JS_FILE"
HEADER_PHP="/var/www/header.php"
SERVICE_FILE="/etc/systemd/system/moode-sse.service"
LOG_FILE="/var/log/radio-cover.log"
NGINX_SITE="/etc/nginx/sites-available/moode-http.conf"

echo ""
echo "============================================="
echo "  moOde-radio-plus — Disinstallazione"
echo "============================================="
echo ""

read -p "  Confermi la disinstallazione? [s/N] " confirm
[[ "$confirm" =~ ^[Ss]$ ]] || { echo "Disinstallazione annullata."; exit 0; }

# — 1. STOP E RIMOZIONE SERVIZIO ——————————
echo "[1/5] Rimozione servizio systemd..."
sudo systemctl stop moode-sse.service    2>/dev/null || true
sudo systemctl disable moode-sse.service 2>/dev/null || true
sudo rm -f "$SERVICE_FILE"
sudo systemctl daemon-reload
echo "  Servizio rimosso."

# — 2. RIMOZIONE SNIPPET DA header.php ——————
echo "[2/5] Rimozione snippet da header.php..."

sudo python3 - <<PYEOF
import re

target = '/var/www/header.php'
js_file = 'moode_radio_plus_snippet.js'

with open(target, 'r') as f:
    content = f.read()

if js_file in content:
    content = re.sub(r'[ \t]*<script src="js/' + js_file + r'\?v=\d+"></script>\n?', '', content)
    with open(target, 'w') as f:
        f.write(content)
    print('  Tag script rimosso da header.php.')
else:
    print('  Tag non trovato in header.php, skip.')
PYEOF

sudo rm -f "${HEADER_PHP}.bak."[0-9]*
echo "  Backup datati rimossi. Il backup originale e conservato in ${HEADER_PHP}.bak.original"

# — 3. RIMOZIONE FILE JS ———————————————
echo "[3/5] Rimozione snippet JS..."
sudo rm -f "$JS_DEST"
echo "  $JS_DEST rimosso."

# — 4. RIPRISTINO NGINX ————————————————
echo "[4/5] Ripristino configurazione Nginx..."
NGINX_BACKUP=$(ls -tr "${NGINX_SITE}.bk."* 2>/dev/null | head -1)

if [ -n "$NGINX_BACKUP" ]; then
    echo "  Ripristino Nginx da backup: $NGINX_BACKUP"
    sudo cp "$NGINX_BACKUP" "$NGINX_SITE"
    sudo rm -f "${NGINX_SITE}.bk."*
elif grep -q "cover-events" "$NGINX_SITE" 2>/dev/null; then
    echo "  Rimozione blocco /cover-events da Nginx..."
    sudo sed -i '/location \/cover-events/,/}/d' "$NGINX_SITE"
else
    echo "  Nessuna modifica Nginx trovata, skip."
fi

if sudo nginx -t 2>/dev/null; then
    sudo nginx -s reload
    echo "  Nginx ripristinato."
else
    echo "  ATTENZIONE: test Nginx fallito. Verifica manuale necessaria."
fi

# — 5. RIMOZIONE DIRECTORY E LOG —————————
echo "[5/5] Rimozione directory e log..."
if [ -d "$INSTALL_DIR" ]; then
    sudo rm -rf "$INSTALL_DIR"
    echo "  Directory $INSTALL_DIR rimossa."
else
    echo "  Directory non trovata, skip."
fi
sudo rm -f "$LOG_FILE"
echo "  Log rimosso."

echo ""
echo "============================================="
echo "  Disinstallazione completata."
echo ""
echo "  Svuota cache kiosk per applicare le modifiche:"
echo "    rm -rf /home/$USER/.cache/chromium"
echo "    sudo systemctl restart localdisplay.service"
echo "============================================="