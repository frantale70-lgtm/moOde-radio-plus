# Relazione Tecnica: Fallimento "Zero-Flash" su Transizioni NAS

> [!NOTE]
> Documento riassuntivo preparato per futuri sviluppi o per l'analisi da parte di altre IA (es. Claude) riguardo all'annoso problema del "flash nero" tra brani NAS su moOde audio player.

## 1. Lo Scopo (L'Obiettivo)
Durante la transizione tra due brani locali (NAS -> NAS), l'interfaccia nativa di moOde aggiorna la copertina (`#coverart-url`) svuotando prima il contenitore o inserendo temporaneamente un placeholder nero/vuoto, per poi caricare la nuova immagine. Questo causa uno sfarfallio nero visivamente fastidioso (black flash) sul Kiosk.
L'obiettivo era intercettare questo evento tramite DOM manipulation (JavaScript) per mantenere a schermo la copertina "vecchia" finché quella "nuova" non fosse completamente scaricata e pronta, realizzando una transizione fluida e invisibile.

## 2. I Tentativi di Fix (V7.0 - V7.10)
Abbiamo tentato di risolvere il problema agendo esclusivamente lato client (browser) tramite un `MutationObserver` applicato agli elementi immagine (es. `COVER_IDS`).

**La logica implementata:**
1. Intercettare l'inserimento della nuova immagine da parte del codice nativo di moOde.
2. Controllare se l'immagine nuova era già in cache (`addedImg.complete`). In caso negativo:
3. Nascondere immediatamente la nuova immagine impostando `display: none`.
4. Reinserire nel DOM l'immagine vecchia (`removedImg`) per mantenere la visuale intatta.
5. Agganciare gli eventi `onload` e `onerror` alla nuova immagine.
6. Al completamento del caricamento (`onload`), eseguire lo *swap*: rendere visibile la nuova (`display: ''`) e distruggere la vecchia (`_old.parentNode.removeChild(_old)`).

## 3. Il Problema Critico sul Kiosk (Chromium Pi)
Mentre sui browser desktop (Chrome/Firefox su PC) la logica funzionava perfettamente ("il browser cammina alla grande"), sul Raspberry Pi collegato al display Kiosk si verificava un blocco catastrofico dell'interfaccia logica.

**I Sintomi sul Kiosk:**
- Contatore del tempo congelato.
- Copertine bloccate permanentemente sull'immagine vecchia.
- **Desync del touch:** Tappando sulla miniatura di una webradio nella griglia, veniva riprodotta la radio della riga sottostante.

**La Causa Architetturale (Bug di Chromium su Pi):**
Il motore Chromium ottimizzato per Raspberry Pi (o in modalità Kiosk) adotta policy aggressive di risparmio risorse. Quando un'immagine viene inserita nel DOM con `display: none`, il browser **sospende o ritarda indefinitamente il download del file multimediale**.
Di conseguenza:
1. L'evento `onload` non scatta **mai**.
2. La funzione di *swap* non viene mai eseguita.
3. Ad ogni cambio brano, il contenitore accumula immagini "fantasma" (`<img class="old">`) invisibili ma fisicamente presenti nel DOM.
4. L'accumulo di nodi HTML spinge il layout della pagina, disallineando le coordinate fisiche del display touch rispetto agli elementi logici cliccabili (spiegando il tap sfasato).

## 4. Decisione Finale e Motivazione
Si è deciso di **abbandonare l'approccio DOM-manipulation client-side** per le transizioni NAS (ritornando alla logica V6 tramite la patch V7.11) e accettare temporaneamente il flash nero.

**Motivazione:**
- La manipolazione forzata del DOM va in conflitto con i cicli di rendering nativi di moOde e i limites del motore Chromium del Pi.
- Qualsiasi approccio basato sul nascondere elementi (tramite `display`, `opacity` o posizionamento assoluto) rischia di innescare memory leak visivi o desync strutturali.
- La soluzione definitiva e più pulita dovrà essere implementata **nativamente nel backend/frontend di moOde** (progetto `moOde-integration`), ad esempio pre-caricando le immagini via JavaScript standard prima di innescare il cambio src, senza dover lottare contro il DOM nativo.

---
*Nota: Questa relazione è archiviata come documentazione tecnica del progetto.*
