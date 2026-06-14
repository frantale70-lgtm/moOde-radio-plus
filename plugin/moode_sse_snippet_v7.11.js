/* moode-sse-patch V7.11 — Rimosso NAS->NAS zero-flash (causa instabilità layout Kiosk) */

;(function () {
    'use strict';

    var lastEventTs    = 0;
    var lastAppliedUrl = null;
    var rafPending     = false;
    var sseActive      = false;
    var pendingUrl     = null;
    var userDisabled   = false;
    var evtSourceRef   = null;
    var savedLogoUrl   = null;

    var COVER_IDS = ['coverart-url', 'playbar-cover', 'cover-backdrop',
                     'ss-backdrop',  'ss-coverart-url'];

    /* — Black Box Logger — */
    function sendLog(msg) {
        try {
            fetch('http://localhost:5000/client-log', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: msg })
            }).catch(function(e){});
        } catch(e) {}
    }

    window.onerror = function(message, source, lineno, colno, error) {
        sendLog('Global Error: ' + message + ' at ' + source + ':' + lineno + ':' + colno);
    };
    window.addEventListener('unhandledrejection', function(event) {
        sendLog('Unhandled Promise Rejection: ' + event.reason);
    });

    sendLog('moode-sse-patch V7.11 initialized. NAS zero-flash rimosso.');
    /* — End Black Box Logger — */

    /* — MR+ Badge — */
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
        if (el && el.src) savedLogoUrl = el.src;
    }

    function restoreLogo() {
        var url = savedLogoUrl;
        if (!url) return;
        var el;
        el = document.querySelector('#coverart-url img');
        if (el) el.src = url;
        el = document.querySelector('#playbar-cover img');
        if (el) el.src = url;
        el = document.querySelector('#cover-backdrop img');
        if (el) el.src = url;
        el = document.querySelector('#ss-coverart-url img');
        if (el) el.src = url;
        el = document.querySelector('#ss-backdrop img');
        if (el) el.src = url;
        if (typeof MPD !== 'undefined' && MPD.json) {
            MPD.json.coverurl = url;
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
            lastAppliedUrl = null;
            if (evtSourceRef) { evtSourceRef.close(); evtSourceRef = null; }
            restoreLogo();
        }
        updateBadge();
    }
    /* — end badge — */

    function extractTs(url) {
        var m = url && url.match(/[?&]t=(\d+)/);
        return m ? parseInt(m[1], 10) : 0;
    }

    function setImgSrcSafe(el, url) {
        if (!el) return;
        el.setAttribute('data-mrplus', '1');
        el.src = url;
    }

    function applyPendingUrl() {
        rafPending = false;
        if (!pendingUrl) return;
        if (!sseActive) { pendingUrl = null; return; }

        try {
            var url = pendingUrl;
            if (typeof UI !== 'undefined') UI.radioCoverUrl = url;

            setImgSrcSafe(document.querySelector('#coverart-url img'), url);
            setImgSrcSafe(document.querySelector('#playbar-cover img'), url);
            
            if (typeof SESSION !== 'undefined' && SESSION.json &&
                    SESSION.json.cover_backdrop === 'Yes') {
                setImgSrcSafe(document.querySelector('#cover-backdrop img'), url);
            }
            setImgSrcSafe(document.querySelector('#ss-coverart-url img'), url);
            setImgSrcSafe(document.querySelector('#ss-backdrop img'), url);

            if (typeof MPD !== 'undefined' && MPD.json) {
                MPD.json.coverurl = url;
            }

            lastAppliedUrl = url;
            pendingUrl     = null;
        } catch (e) {
            sendLog('Error in applyPendingUrl: ' + e);
        }
    }

    function scheduleApply() {
        if (rafPending) return;
        rafPending = true;
        setTimeout(applyPendingUrl, 50);
    }

    function enqueueCoverUpdate(url) {
        var ts = extractTs(url);
        if (ts <= lastEventTs) return;
        lastEventTs = ts;
        lastAppliedUrl = url;
        pendingUrl  = url;
        scheduleApply();
    }

    function installJqueryHtmlIntercept() {
        function tryInstall() {
            if (typeof $ === 'undefined' || !$.fn) {
                setTimeout(tryInstall, 200);
                return;
            }
            var _origHtml = $.fn.html;
            $.fn.html = function (content) {
                try {
                    if (content !== undefined && sseActive &&
                            lastAppliedUrl && this.length && this[0]) {
                        var id = this[0].id;
                        if (id && COVER_IDS.indexOf(id) !== -1) {
                            return this;
                        }
                    }
                } catch(e) { sendLog('Error in $.fn.html intercept: ' + e); }
                return _origHtml.apply(this, arguments);
            }
            sendLog('$.fn.html intercepted successfully.');
        }
        tryInstall();
    }

    function installMutationGuard() {
        function tryInstall() {
            var found = COVER_IDS.some(function(id) {
                return document.getElementById(id);
            });
            if (!found) { setTimeout(tryInstall, 300); return; }

            var observer = new MutationObserver(function(mutations) {
                mutations.forEach(function(mutation) {

                    if (mutation.type === 'attributes' &&
                            mutation.attributeName === 'src') {

                        var img    = mutation.target;
                        var parent = img.parentElement;
                        if (!parent) return;

                        var inCoverDiv = COVER_IDS.some(function(id) {
                            return parent.id === id;
                        });
                        if (!inCoverDiv) return;
                        
                        /* BULLETPROOF: Ignora se l'abbiamo cambiato noi */
                        if (img.getAttribute('data-mrplus') === '1') {
                            img.removeAttribute('data-mrplus');
                            return;
                        }

                        if (sseActive) {
                            /* SSE attivo: blocca sovrascrittura nativa */
                            if (lastAppliedUrl) {
                                setImgSrcSafe(img, lastAppliedUrl);
                            }
                        }
                    }
                });
            });

            COVER_IDS.forEach(function(id) {
                var el = document.getElementById(id);
                if (el) {
                    observer.observe(el, {
                        attributes:      true,
                        attributeFilter: ['src'],
                        subtree:         true
                    });
                }
            });
            sendLog('MutationGuard installed (V7.11 mode).');
        }
        tryInstall();
    }

    function installMpdInterceptor() {
        function tryInstall() {
            if (typeof MPD === 'undefined') { setTimeout(tryInstall, 200); return; }
            var _json = MPD.json || 0;
            Object.defineProperty(MPD, 'json', {
                get: function () { return _json; },
                set: function (val) {
                    _json = val;
                    try {
                        if (val && typeof val === 'object' && val.coverurl &&
                                val.coverurl.indexOf('/coverart.php/') === 0) {
                            sseActive      = false;
                            lastAppliedUrl = null;
                            updateBadge();
                            return;
                        }
                        if (sseActive && lastAppliedUrl && val && typeof val === 'object') {
                            val.coverurl = lastAppliedUrl;
                        }
                    } catch(e) { sendLog('Error in MPD.json setter: ' + e); }
                },
                configurable: true
            });
            sendLog('MPD Interceptor installed successfully.');
        }
        tryInstall();
    }

    function initSSE() {
        if (userDisabled) return;
        captureLogo();
        var evtSource = new EventSource('/cover-events');
        evtSourceRef = evtSource;

        evtSource.onopen = function () {
            if (userDisabled) { evtSource.close(); return; }
            sseActive = true;
            captureLogo();
            updateBadge();
            sendLog('SSE Connection Opened.');
            if (lastAppliedUrl) {
                pendingUrl = lastAppliedUrl;
                scheduleApply();
            }
        };

        evtSource.onmessage = function (e) {
            if (userDisabled) return;
            try {
                var data = JSON.parse(e.data);
                if (data.event === 'cover_updated' && data.cover_url) {
                    sseActive = true;
                    captureLogo();
                    updateBadge();
                    enqueueCoverUpdate(data.cover_url);
                } else if (data.event === 'logo_restored' && data.cover_url) {
                    enqueueCoverUpdate(data.cover_url);
                }
            } catch (err) {
                sendLog('Error parsing SSE message: ' + err);
            }
        };

        evtSource.onerror = function () {
            sendLog('SSE Connection Error/Closed.');
            sseActive = false;
            updateBadge();
            evtSource.close();
            evtSourceRef = null;
            if (!userDisabled) setTimeout(initSSE, 5000);
        };
    }

    installJqueryHtmlIntercept();
    installMutationGuard();
    installMpdInterceptor();
    window._sseDebug = function () {
        return { sseActive: sseActive, lastAppliedUrl: lastAppliedUrl, pendingUrl: pendingUrl, userDisabled: userDisabled, savedLogoUrl: savedLogoUrl };
    };
    sendLog('Starting initial SSE connection.');
    initSSE();

    if (document.body) { createBadge(); }
    else { document.addEventListener('DOMContentLoaded', createBadge); }

})();