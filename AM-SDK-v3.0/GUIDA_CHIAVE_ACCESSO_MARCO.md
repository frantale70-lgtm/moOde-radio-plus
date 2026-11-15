# 🔐 Guida Rapida: Generare la Chiave di Accesso Privata per Marco

1. Apri [https://github.com/settings/personal-access-tokens/new](https://github.com/settings/personal-access-tokens/new)
2. **Token name:** `marco-am-sdk-v3-readonly`
3. **Repository access:** **Only select repositories** -> `ai-autopilot-lab`
4. **Permissions -> Repository permissions -> Contents:** **`Read-only`**
5. Invia a Marco la chiave `github_pat_...` con i comandi:

```powershell
git clone https://<INSERISCI_QUI_LA_CHIAVE_GITHUB_PAT>@github.com/frantale70-lgtm/ai-autopilot-lab.git C:\Users\$env:USERNAME\am-sdk-autopilot
cd C:\Users\$env:USERNAME\am-sdk-autopilot
powershell -ExecutionPolicy Bypass -File .\install_am_sdk.ps1
```
