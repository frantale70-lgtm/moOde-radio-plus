#!/bin/bash
# ============================================================
#  moOde-radio-plus — Install Script
#  Target: moOde Audio Player 10.2.0 on Raspberry Pi 4
#  Repo:   https://github.com/frantale70-lgtm/moOde-radio-plus
# ============================================================

set -e

REPO_RAW="https://raw.githubusercontent.com/frantale70-lgtm/moOde-radio-plus/main"
INSTALL_DIR="/opt/moOde_Radio_Cover"
JS_TARGET="/var/www/js/lib.min.js"
SERVICE_FILE="/etc/systemd/system/moode-sse.service"
LOG_FILE="/var/log/radio-cover.log"
LOGOS_DIR="/var/local/www/imagesw/radio-logos"

echo ""
echo "============================================="
echo "  moOde-radio-plus — Installazione"
echo "============================================="
echo ""

# ── PREREQUISITO ─────────────────────────────────
echo "[1/6] Prerequisito moOde..."
echo "  Assicurati che in moOde:"
echo "  Preferences → Cover Art → Radio track covers = No"
read -p "  Confermato? [s/N] " confirm
[[ "$confirm" =~ ^[Ss]$ ]] || { echo "Installazione annullata."; exit 1; }

# ── CARTELLE ─────────────────────────────────────
echo "[2/6] Creazione cartelle..."
sudo mkdir -p "$INSTALL_DIR"
sudo mkdir -p "$LOGOS_DIR"
sudo touch "$LOG_FILE"

# ── PERMESSI ─────────────────────────────────────
echo "[3/6] Assegnazione permessi..."
sudo chown root:www-data "$INSTALL_DIR"
sudo chmod 755 "$INSTALL_DIR"
sudo chown root:www-data "$LOG_FILE"
sudo chmod 664 "$LOG_FILE"
sudo chown root:www-data "$LOGOS_DIR"
sudo chmod 755 "$LOGOS_DIR"

# ── DOWNLOAD FILE ─────────────────────────────────
echo "[4/6] Download file dal repository..."

# Daemon
sudo curl -fsSL "$REPO_RAW/plugin/moode_sse_server.py" \
    -o "$INSTALL_DIR/moode_sse_server.py"
sudo chown root:root "$INSTALL_DIR/moode_sse_server.py"
sudo chmod 644 "$INSTALL_DIR/moode_sse_server.py"

# Config
sudo curl -fsSL "$REPO_RAW/plugin/moode_sse_server.config" \
    -o "$INSTALL_DIR/moode_sse_server.config"
sudo chown root:root "$INSTALL_DIR/moode_sse_server.config"
sudo chmod 600 "$INSTALL_DIR/moode_sse_server.config"

# lib.min.js — backup + append snippet
echo "  Backup lib.min.js..."
sudo cp "$JS_TARGET" "${JS_TARGET}.bk.$(date +%Y%m%d_%H%M%S)"
sudo curl -fsSL "$REPO_RAW/plugin/moode_sse_snippet_v6.js" \
    | sudo tee -a "$JS_TARGET" > /dev/null
sudo chown root:root "$JS_TARGET"
sudo chmod 644 "$JS_TARGET"

# ── SERVIZIO SYSTEMD ──────────────────────────────
echo "[5/6] Installazione servizio systemd..."
sudo curl -fsSL "$REPO_RAW/plugin/moode-sse.service" \
    -o "$SERVICE_FILE"
sudo chown root:root "$SERVICE_FILE"
sudo chmod 644 "$SERVICE_FILE"
sudo systemctl daemon-reload
sudo systemctl enable moode-sse.service
sudo systemctl restart moode-sse.service

# ── VERIFICA ─────────────────────────────────────
echo "[6/6] Verifica servizio..."
sleep 2
if systemctl is-active --quiet moode-sse.service; then
    echo ""
    echo "  ✅ moode-sse attivo e in esecuzione."
else
    echo ""
    echo "  ❌ Servizio non avviato. Controlla il log:"
    echo "     tail -f $LOG_FILE"
    exit 1
fi

echo ""
echo "============================================="
echo "  Installazione completata."
echo ""
echo "  ⚠ IMPORTANTE: Inserisci le API keys in:"
echo "    $INSTALL_DIR/moode_sse_server.config"
echo ""
echo "  Poi riavvia il daemon:"
echo "    sudo systemctl restart moode-sse"
echo ""
echo "  Svuota cache kiosk:"
echo "    rm -rf /home/moode/.cache/chromium"
echo "    sudo systemctl restart localdisplay.service"
echo "============================================="
