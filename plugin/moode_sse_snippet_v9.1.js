/* moode-sse-patch V9.1 — Native jQuery DOM + MR+ Interactive Badge */
;(function () {
    'use strict';

    // Attendi che jQuery sia disponibile (moOde lo carica in modo asincrono)
    function waitForJQuery(cb) {
        if (window.jQuery) {
            cb(window.jQuery);
        } else {
            setTimeout(function() { waitForJQuery(cb); }, 100);
        }
    }

    waitForJQuery(function($) {

        var currentCoverUrl = '';
        var DEFAULT_COVER = '/images/default-cover-v6.svg';
        
        var userDisabled = false;
        var sseActive = false;
        var savedLogoUrl = null;
        var evtSourceRef = null;

        /* — MR+ Badge UI — */
        function createBadge() {
            var hideStyle = document.createElement('style');
            hideStyle.innerHTML = '#format-badge, .audio-format, #cover-badge, .cover-badge, #audio-badge, .format-badge { display: none !important; }';
            document.head.appendChild(hideStyle);

            var badge = document.createElement('div');
            badge.id = 'mrplus-badge';
            badge.textContent = 'MR+';
            badge.style.cssText =
                'position:fixed;bottom:12px;right:12px;z-index:9999;' +
                'background:rgba(0,180,220,0.7);color:#fff;' +
                'font-family:monospace;font-size:14px;font-weight:bold;' +
                'padding:6px 12px;border-radius:4px;border:none;outline:none;' +
                'box-shadow:none;line-height:normal;margin:0;' +
                'cursor:pointer;opacity:0.7;' +
                'transition:opacity 0.3s,background 0.3s;' +
                '-webkit-tap-highlight-color:transparent;';
            badge.addEventListener('click', togglePlugin);
            badge.addEventListener('touchend', function(e) { e.preventDefault(); togglePlugin(); });
            document.body.appendChild(badge);
            return badge;
        }

        function updateBadge() {
            var badge = document.getElementById('mrplus-badge');
            if (!badge) badge = createBadge();
            if (userDisabled) {
                badge.style.background = 'rgba(0,180,220,0.7)';
                badge.style.opacity = '0.4';
                badge.textContent = 'MR-';
            } else if (sseActive) {
                badge.style.background = 'rgba(220,200,0,0.9)';
                badge.style.opacity = '0.9';
                badge.textContent = 'MR+';
            } else {
                badge.style.background = 'rgba(0,180,220,0.7)';
                badge.style.opacity = '0.5';
                badge.textContent = 'MR+';
            }
        }

        function captureLogo() {
            if (savedLogoUrl) return;
            var el = document.querySelector('#coverart-url img');
            if (el && el.src && !el.src.includes('default-cover')) {
                savedLogoUrl = el.src;
            }
        }

        function togglePlugin() {
            if (userDisabled) {
                userDisabled = false;
                savedLogoUrl = null;
                initSSE();
            } else {
                userDisabled = true;
                sseActive = false;
                if (evtSourceRef) { evtSourceRef.close(); evtSourceRef = null; }
                
                if (currentCoverUrl !== '') {
                    currentCoverUrl = '';
                    if (savedLogoUrl) {
                        applyNativeCover(savedLogoUrl);
                    } else {
                        applyNativeCover('');
                    }
                }
            }
            updateBadge();
        }
        /* — End MR+ Badge UI — */

        // Applica la copertina usando esattamente il pattern nativo di moOde
        function applyNativeCover(url) {
            if (!url) {
                // Ripristina il default esattamente come fa moOde
                $('#coverart-url').html('<img class="coverart" src="' + DEFAULT_COVER + '" alt="Cover art not found">');
                $('#playbar-cover').html('<img src="' + DEFAULT_COVER + '">');
                $('#ss-coverart-url').html($('#coverart-url').html());
            } else {
                $('#coverart-url').html('<img class="coverart" src="' + url + '" alt="Cover art not found">');
                $('#playbar-cover').html('<img src="' + url + '">');
                $('#ss-coverart-url').html($('#coverart-url').html());
            }
        }

        // Precarica l'immagine prima di iniettarla nel DOM
        function preloadAndApply(url) {
            if (url === currentCoverUrl) return; // Idempotenza
            currentCoverUrl = url;

            var img = new Image();
            img.onload = function() {
                if (currentCoverUrl === url) {
                    applyNativeCover(url);
                }
            };
            img.onerror = function() {
                // Immagine non raggiungibile: resetta silenziosamente
                if (currentCoverUrl === url) {
                    currentCoverUrl = '';
                    applyNativeCover('');
                }
            };
            img.src = url;
        }

        // Connessione SSE al backend Python
        function initSSE() {
            if (userDisabled) return;
            captureLogo();
            
            var evtSource = new EventSource('http://' + window.location.hostname + ':5000/cover-events');
            evtSourceRef = evtSource;

            evtSource.onopen = function() {
                if (userDisabled) { evtSource.close(); return; }
                sseActive = true;
                captureLogo();
                updateBadge();
                console.log('[SSE] v9.1: connection opened');
            };

            evtSource.onmessage = function(e) {
                if (userDisabled) return;
                try {
                    var data = JSON.parse(e.data);
                    if (data.event === 'cover_updated' && data.cover_url) {
                        sseActive = true;
                        captureLogo();
                        updateBadge();
                        preloadAndApply(data.cover_url);
                    } else if (data.event === 'logo_restored') {
                        if (currentCoverUrl !== '') {
                            currentCoverUrl = '';
                            // Lascia che moOde ripristini il logo originale nativamente
                            // In V9.1 non forziamo savedLogoUrl qui per non litigare con la UI nativa, 
                            // ci penserà moOde, o se siamo in fallback ripristina la default
                        }
                    }
                } catch (err) {}
            };

            evtSource.onerror = function() {
                // Silenzio assoluto: la copertina rimane a schermo durante la riconnessione
                sseActive = false;
                updateBadge();
                evtSource.close();
                evtSourceRef = null;
                console.log('[SSE] v9.1: connection error, retrying silently...');
                if (!userDisabled) setTimeout(initSSE, 5000);
            };
        }

        // MutationObserver: se moOde cambia copertina nativamente (es. zapping NAS),
        // invalidiamo il nostro stato senza toccare il DOM
        function setupObserver() {
            var moodeCover = document.querySelector('#coverart-url img');
            if (moodeCover) {
                new MutationObserver(function() {
                    var src = moodeCover.getAttribute('src');
                    // Se moOde ha inserito qualcosa di diverso dalla nostra copertina, cediamo il controllo
                    if (src && src !== currentCoverUrl && !src.includes('default-cover')) {
                        currentCoverUrl = '';
                        // Se moOde sta caricando una cover nuova (non generica), salviamola come logo
                        if (!userDisabled && !sseActive) {
                            savedLogoUrl = src;
                        }
                    }
                }).observe(moodeCover, { attributes: true, attributeFilter: ['src'] });
                console.log('[SSE] moode-sse-patch v9.1: observer attached');
            } else {
                setTimeout(setupObserver, 500);
            }
        }

        setupObserver();
        
        if (document.body) { createBadge(); }
        else { document.addEventListener('DOMContentLoaded', createBadge); }
        
        initSSE();
        console.log('[SSE] moode-sse-patch v9.1 loaded');

    }); // end waitForJQuery

})();