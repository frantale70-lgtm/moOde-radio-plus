#!/bin/bash
# ============================================================
#  moOde-radio-plus — Uninstall Script (Arch B)
#  Target: moOde Audio Player 10.2.x on Raspberry Pi 4
#  Repo:   https://github.com/frantale70-lgtm/moOde-radio-plus
# ============================================================

set -e

INSTALL_DIR="/opt/moOde_Radio_Cover"
SNIPPET_FILE="moode_sse_snippet.js"
JS_DIR="/var/www/js"
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

# — 1. STOP E RIMOZIONE SERVIZIO ————————————————
echo "[1/5] Rimozione servizio systemd..."
sudo systemctl stop moode-sse.service    2>/dev/null || true
sudo systemctl disable moode-sse.service 2>/dev/null || true
sudo rm -f "$SERVICE_FILE"
sudo systemctl daemon-reload
echo "  Servizio rimosso."

# — 2. RIPRISTINO HEADER.PHP ————————————————————
echo "[2/5] Ripristino header.php..."
if [ -f "${HEADER_PHP}.bak.original" ]; then
    sudo cp "${HEADER_PHP}.bak.original" "$HEADER_PHP"
    sudo rm -f "${HEADER_PHP}.bak."*
    echo "  header.php ripristinato dal backup originale."
else
    echo "  Backup originale non trovato — rimozione tag via Python..."
    sudo python3 - << PYEOF
import re, sys

target = '$HEADER_PHP'
snippet = '$SNIPPET_FILE'

with open(target, 'r') as f:
    content = f.read()

if snippet in content:
    content = re.sub(
        r'\s*<script src="js/' + re.escape(snippet) + r'\?v=\d+" defer></script>\n?',
        '',
        content
    )
    with open(target, 'w') as f:
        f.write(content)
    print("  Tag rimosso da header.php.")
else:
    print("  Tag non trovato in header.php, skip.")
PYEOF
fi

# — 2b. RIMOZIONE FILE JS STANDALONE ———————————
if [ -f "$JS_DIR/$SNIPPET_FILE" ]; then
    sudo rm -f "$JS_DIR/$SNIPPET_FILE"
    echo "  $SNIPPET_FILE rimosso da $JS_DIR."
else
    echo "  $SNIPPET_FILE non trovato, skip."
fi

# — 3. RIPRISTINO NGINX ————————————————————————
echo "[3/5] Ripristino configurazione Nginx..."
NGINX_BACKUP=$(ls -tr "${NGINX_SITE}.bk."* 2>/dev/null | head -1)

if [ -n "$NGINX_BACKUP" ]; then
    sudo cp "$NGINX_BACKUP" "$NGINX_SITE"
    sudo rm -f "${NGINX_SITE}.bk."*
    echo "  Nginx ripristinato da backup."
elif grep -q "cover-events" "$NGINX_SITE" 2>/dev/null; then
    sudo sed -i '/location \/cover-events/,/}/d' "$NGINX_SITE"
    echo "  Blocco /cover-events rimosso da Nginx."
else
    echo "  Nessuna modifica Nginx trovata, skip."
fi

if sudo nginx -t 2>/dev/null; then
    sudo nginx -s reload
    echo "  Nginx ripristinato."
else
    echo "  ATTENZIONE: test Nginx fallito. Verifica manuale necessaria."
fi

# — 4. RIMOZIONE DIRECTORY E LOG ———————————————
echo "[4/5] Rimozione directory e log..."
if [ -d "$INSTALL_DIR" ]; then
    CONFIG_FILE="$INSTALL_DIR/moode_sse_server.config"
    if [ -f "$CONFIG_FILE" ]; then
        read -p "  Conservare il file config con le API keys? [S/n] " keep_config
        if [[ ! "$keep_config" =~ ^[Nn]$ ]]; then
            CURRENT_USER=$(whoami)
            sudo cp "$CONFIG_FILE" /home/"$CURRENT_USER"/moode_sse_server.config.saved
            echo "  Config salvato in /home/$CURRENT_USER/moode_sse_server.config.saved"
        fi
    fi
    sudo rm -rf "$INSTALL_DIR"
    echo "  Directory $INSTALL_DIR rimossa."
else
    echo "  Directory non trovata, skip."
fi
sudo rm -f "$LOG_FILE"
echo "  Log rimosso."

# — 5. SVUOTAMENTO CACHE KIOSK ————————————————
echo "[5/5] Svuotamento cache kiosk..."
CURRENT_USER=$(whoami)
sudo rm -rf /home/"$CURRENT_USER"/.cache/chromium 2>/dev/null || true
echo "  Cache rimossa."

echo ""
echo "============================================="
echo "  Disinstallazione completata."
echo ""
echo "  Per rendere effettive le modifiche a video:"
echo "    sudo systemctl restart localdisplay.service"
echo "============================================="
