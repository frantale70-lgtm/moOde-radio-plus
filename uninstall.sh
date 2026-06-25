#!/bin/bash
# ============================================================
#  moOde-radio-plus — Uninstall Script
#  Target: moOde Audio Player 10.2.x on Raspberry Pi 4
#  Repo:   https://github.com/frantale70-lgtm/moOde-radio-plus
# ============================================================

set -e

INSTALL_DIR="/opt/moOde_Radio_Cover"
LIB_MIN="/var/www/js/lib.min.js"
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

# — 1. STOP E RIMOZIONE SERVIZIO —
echo "[1/5] Rimozione servizio systemd..."
sudo systemctl stop moode-sse.service    2>/dev/null || true
sudo systemctl disable moode-sse.service 2>/dev/null || true
sudo rm -f "$SERVICE_FILE"
sudo systemctl daemon-reload
echo "  Servizio rimosso."

# — 2. RIPRISTINO lib.min.js —
echo "[2/5] Ripristino lib.min.js..."
if [ -f "${LIB_MIN}.bak.original" ]; then
    sudo cp "${LIB_MIN}.bak.original" "$LIB_MIN"
    sudo rm -f "${LIB_MIN}.bak."*
    echo "  lib.min.js ripristinato dal backup originale."
else
    echo "  ATTENZIONE: Backup originale non trovato."
    if grep -q "moode-sse-patch" "$LIB_MIN" 2>/dev/null; then
        echo "  Rimozione manuale dello snippet dal file..."
        sudo sed -i '/moode-sse-patch/,$d' "$LIB_MIN"
        echo "  Snippet rimosso."
    else
        echo "  Snippet non trovato in lib.min.js, skip."
    fi
fi

# — 3. RIPRISTINO NGINX —
echo "[3/5] Ripristino configurazione Nginx..."
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

# — 4. RIMOZIONE DIRECTORY E LOG —
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