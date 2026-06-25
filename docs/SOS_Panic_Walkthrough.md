# Walkthrough: Sistema di Fallback "SOS Install Panic"

Abbiamo completato la creazione di un sistema di emergenza impermeabile, ideato per salvaguardare il repository e le installazioni sui Raspberry da futuri test potenzialmente distruttivi.

## Cosa è stato implementato

1. **Creazione dell'ambiente isolato (`obsolete/`)**
   Abbiamo inaugurato la cartella `obsolete` per ospitare versioni funzionanti da conservare come paracadute. La prima capsula di salvataggio è `v7.11_lib_min_injection`, che incapsula la versione più robusta testata finora.

2. **Isolamento "Stagno" degli Script**
   I 4 file vitali (`moode_sse_server.py`, `moode_sse_server.config`, `moode-sse.service`, e lo snippet JS) sono stati duplicati all'interno della cartella `v7.11_lib_min_injection`.
   L'`install.sh` di backup è stato modificato in modo che peschino **esclusivamente** da quella specifica directory, garantendo che non scaricherà mai per errore un file rotto proveniente dalla directory principale `plugin/`.

3. **Script di Rollback (`reverse_install.sh`)**
   È stato creato uno script nella root del progetto. Se lanciato, questo script:
   - Disinstalla la versione difettosa in corso.
   - Si sposta nell'ambiente isolato V7.11.
   - Reinstalla la versione "ancora di salvezza", riportando il Raspberry a uno stato perfettamente funzionante.

4. **Documentazione aggiornata**
   Il file `README.md` è stato aggiornato con una nuova sezione "SOS Install Panic" per istruire la community (e noi stessi) su come utilizzare questo sistema in caso di emergenza.

> **Come usare il sistema in futuro:** 
> Se domani tu e Claude proverete a fare una "V8" usando i `<defer>` su `header.php` o altre iniezioni sperimentali, e il Raspberry dovesse andare in kernel panic o smettere di mostrare le copertine, ti basterà lanciare `bash reverse_install.sh` e il sistema tornerà in 10 secondi alla V7.11 funzionante, senza alcuna perdita di dati o nottate perse a fare debug.
