#!/bin/bash
# ============================================================
#  moOde-radio-plus — Uninstall Script
#  Target: moOde Audio Player 10.2.0 on Raspberry Pi 4
#  Repo:   https://github.com/frantale70-lgtm/moOde-radio-plus
# ============================================================

set -e

INSTALL_DIR="/opt/moOde_Radio_Cover"
JS_TARGET="/var/www/js/lib.min.js"
SERVICE_FILE="/etc/systemd/system/moode-sse.service"
LOG_FILE="/var/log/radio-cover.log"

echo ""
echo "============================================="
echo "  moOde-radio-plus — Disinstallazione"
echo "============================================="
echo ""

read -p "  Confermi la disinstallazione? [s/N] " confirm
[[ "$confirm" =~ ^[Ss]$ ]] || { echo "Disinstallazione annullata."; exit 0; }

# ── 1. STOP E RIMOZIONE SERVIZIO ─────────────────────
echo "[1/4] Rimozione servizio systemd..."
sudo systemctl stop moode-sse.service    2>/dev/null || true
sudo systemctl disable moode-sse.service 2>/dev/null || true
sudo rm -f "$SERVICE_FILE"
sudo systemctl daemon-reload
echo "  Servizio rimosso."

# ── 2. RIPRISTINO lib.min.js ───────────────────────
echo "[2/4] Ripristino lib.min.js..."

# Cerca il backup più recente creato dall'installer
BACKUP=$(ls -t "${JS_TARGET}.bk."* 2>/dev/null | head -1)

if [ -n "$BACKUP" ]; then
    echo "  Ripristino da backup: $BACKUP"
    sudo cp "$BACKUP" "$JS_TARGET"
    sudo rm -f "${JS_TARGET}.bk."*
    echo "  lib.min.js ripristinato dal backup."
else
    # Nessun backup: rimuove lo snippet cercando il marcatore
    echo "  Nessun backup trovato. Rimozione snippet tramite marcatore..."
    MARKER="/* moode-sse-patch"
    LINE=$(grep -n "$MARKER" "$JS_TARGET" 2>/dev/null | tail -1 | cut -d: -f1)
    if [ -n "$LINE" ]; then
        sudo head -n $((LINE - 1)) "$JS_TARGET" > /tmp/_lib_min_tmp.js
        sudo mv /tmp/_lib_min_tmp.js "$JS_TARGET"
        echo "  Snippet rimosso (riga $LINE)."
    else
        echo "  Marcatore non trovato in lib.min.js. Nessuna modifica."
    fi
fi

# Ripristino permessi originali
sudo chown root:root "$JS_TARGET"
sudo chmod 644 "$JS_TARGET"
echo "  Permessi ripristinati."

# ── 3. RIMOZIONE DIRECTORY INSTALLAZIONE ──────────────
echo "[3/4] Rimozione directory $INSTALL_DIR..."
if [ -d "$INSTALL_DIR" ]; then
    sudo rm -rf "$INSTALL_DIR"
    echo "  Directory rimossa."
else
    echo "  Directory non trovata, skip."
fi

# ── 4. RIMOZIONE LOG ──────────────────────────────
echo "[4/4] Rimozione log..."
sudo rm -f "$LOG_FILE"
echo "  Log rimosso."

echo ""
echo "============================================="
echo "  Disinstallazione completata."
echo ""
echo "  Svuota cache kiosk per applicare le modifiche:"
echo "    rm -rf /home/moode/.cache/chromium"
echo "    sudo systemctl restart localdisplay.service"
echo "============================================="
