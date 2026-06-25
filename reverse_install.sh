#!/bin/bash
echo "============================================="
echo "   REVERSE INSTALL - FALLBACK DI EMERGENZA"
echo "============================================="
echo "Questo script disinstallerà la versione attuale"
echo "e ripristinerà l'ultima versione stabile:"
echo "-> V7.11 (Iniezione diretta in lib.min.js)"
echo "============================================="
echo ""
read -p "Sei sicuro di voler effettuare il rollback? [s/N] " confirm
if [[ ! "$confirm" =~ ^[Ss]$ ]]; then
    echo "Rollback annullato."
    exit 0
fi

echo ""
echo "[FASE 1] Disinstallazione versione corrente..."
if [ -f "./uninstall.sh" ]; then
    bash ./uninstall.sh
else
    echo "Nessun uninstall.sh trovato nella root. Skippato."
fi

echo ""
echo "[FASE 2] Installazione versione di emergenza..."
cd obsolete/v7.11_lib_min_injection
if [ -f "./install.sh" ]; then
    bash ./install.sh
else
    echo "ERRORE: install.sh di emergenza non trovato!"
    exit 1
fi
cd ../..

echo ""
echo "============================================="
echo "Rollback di emergenza completato con successo."
echo "============================================="