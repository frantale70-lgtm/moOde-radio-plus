/* moode-sse-patch V7.8 — Kiosk RAF Freeze Fix */

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

    /* — MR+ Badge — */
    function createBadge() {
        var badge = document.createElement('div');
        badge.id = 'mrplus-badge';
        badge.textContent = 'MR+';
        badge.style.cssText =
            'position:fixed;bottom:12px;right:12px;z-index:9999;' +
            'background:rgba(0,180,220,0.7);color:#fff;' +
            'font-family:monospace;font-size:14px;font-weight:bold;' +
            'padding:6px 12px;border-radius:4px;' +
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

    function isBadged(url) {
        return url && url.indexOf('?t=') !== -1;
    }

    /* — hold src during load — */
    function holdImgSrc(img, oldSrc, newSrc) {
        img.src = oldSrc;
        var tmp = new Image();
        tmp.onload = function() {
            if (img.parentNode) img.src = newSrc;
        };
        tmp.onerror = function() {
            if (img.parentNode) img.src = newSrc;
        };
        tmp.src = newSrc;
    }

    function applyPendingUrl() {
        rafPending = false;
        if (!pendingUrl) return;
        if (!sseActive) { pendingUrl = null; return; }

        var url = pendingUrl;
        if (typeof UI !== 'undefined') UI.radioCoverUrl = url;

        var el;
        el = document.querySelector('#coverart-url img');
        if (el) el.src = url;
        el = document.querySelector('#playbar-cover img');
        if (el) el.src = url;
        if (typeof SESSION !== 'undefined' && SESSION.json &&
                SESSION.json.cover_backdrop === 'Yes') {
            el = document.querySelector('#cover-backdrop img');
            if (el) el.src = url;
        }
        el = document.querySelector('#ss-coverart-url img');
        if (el) el.src = url;
        el = document.querySelector('#ss-backdrop img');
        if (el) el.src = url;

        if (typeof MPD !== 'undefined' && MPD.json) {
            MPD.json.coverurl = url;
        }

        lastAppliedUrl = url;
        pendingUrl     = null;
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
                if (content !== undefined && sseActive &&
                        lastAppliedUrl && this.length && this[0]) {
                    var id = this[0].id;
                    if (id && COVER_IDS.indexOf(id) !== -1) {
                        return this;
                    }
                }
                return _origHtml.apply(this, arguments);
            }
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

                    if (mutation.type === 'childList') {
                        if (sseActive) return;

                        var container = mutation.target;
                        var inCoverDiv = COVER_IDS.some(function(id) {
                            return container.id === id;
                        });
                        if (!inCoverDiv) return;

                        var removedImg = null;
                        mutation.removedNodes.forEach(function(n) {
                            if (n.tagName === 'IMG') removedImg = n;
                        });
                        var addedImg = null;
                        mutation.addedNodes.forEach(function(n) {
                            if (n.tagName === 'IMG') addedImg = n;
                        });

                        if (!removedImg || !addedImg) return;

                        var oldSrc = removedImg.getAttribute('src');
                        var newSrc = addedImg.getAttribute('src');

                        if (!oldSrc || !newSrc) return;
                        if (newSrc.indexOf('/coverart.php/') !== 0) return;
                        if (oldSrc === newSrc) return;
                        if (addedImg.complete) return;

                        addedImg.style.display = 'none';
                        container.insertBefore(removedImg, addedImg);

                        var _old  = removedImg;
                        var _new  = addedImg;
                        var _done = false;

                        var swap = function () {
                            if (_done) return;
                            _done = true;
                            _new.style.display = '';
                            if (_old.parentNode) _old.parentNode.removeChild(_old);
                        };

                        addedImg.onload  = swap;
                        addedImg.onerror = swap;
                        return;
                    }

                    if (mutation.type === 'attributes' &&
                            mutation.attributeName === 'src') {

                        var img    = mutation.target;
                        var parent = img.parentElement;
                        if (!parent) return;

                        var inCoverDiv = COVER_IDS.some(function(id) {
                            return parent.id === id;
                        });
                        if (!inCoverDiv) return;

                        var newSrc = img.getAttribute('src');
                        var oldSrc = mutation.oldValue;

                        if (sseActive) {
                            /* SSE attivo: blocca sovrascrittura */
                            if (isBadged(newSrc)) {
                                lastAppliedUrl = newSrc;
                            } else {
                                if (lastAppliedUrl) img.src = lastAppliedUrl;
                            }
                            return;
                        }

                        /* SSE inattivo: Radio->NAS transition */
                        if (oldSrc && isBadged(oldSrc) &&
                                newSrc && newSrc.indexOf('/coverart.php/') === 0) {
                            holdImgSrc(img, oldSrc, newSrc);
                        }
                    }
                });
            });

            COVER_IDS.forEach(function(id) {
                var el = document.getElementById(id);
                if (el) {
                    observer.observe(el, {
                        childList:       true,
                        attributes:      true,
                        attributeFilter: ['src'],
                        attributeOldValue: true,
                        subtree:         true
                    });
                }
            });
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
                },
                configurable: true
            });
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
            } catch (_) {}
        };

        evtSource.onerror = function () {
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
    console.log('[SSE] moode-sse-patch v7.8 loaded');
    initSSE();

    if (document.body) { createBadge(); }
    else { document.addEventListener('DOMContentLoaded', createBadge); }

})();