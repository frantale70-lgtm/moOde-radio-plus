/* moode-sse-patch V6 */

;(function () {
    'use strict';

    // ── State ────────────────────────────────────────────────────────────────
    var lastEventTs    = 0;
    var lastAppliedUrl = null;
    var rafPending     = false;
    var sseActive      = false;
    var pendingUrl     = null;

    var COVER_IDS = ['coverart-url', 'playbar-cover', 'cover-backdrop',
                     'ss-backdrop',  'ss-coverart-url'];

    // ── Helpers ──────────────────────────────────────────────────────────────
    function extractTs(url) {
        var m = url && url.match(/[?&]t=(\d+)/);
        return m ? parseInt(m[1], 10) : 0;
    }

    function isBadged(url) {
        return url && url.indexOf('?t=') !== -1;
    }

    // ── DOM apply ────────────────────────────────────────────────────────────
    function applyPendingUrl() {
        rafPending = false;
        if (!pendingUrl) return;

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
        requestAnimationFrame(applyPendingUrl);
    }

    function enqueueCoverUpdate(url) {
        var ts = extractTs(url);
        if (ts <= lastEventTs) return;
        lastEventTs = ts;
        pendingUrl  = url;
        scheduleApply();
    }

    // ── Layer 1: $.fn.html intercept ─────────────────────────────────────────
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
            };
        }
        tryInstall();
    }

    // ── Layer 2: MutationObserver ─────────────────────────────────────────────
    function installMutationGuard() {
        function tryInstall() {
            var found = COVER_IDS.some(function(id) {
                return document.getElementById(id);
            });
            if (!found) { setTimeout(tryInstall, 300); return; }

            var observer = new MutationObserver(function(mutations) {
                if (!sseActive) return;

                mutations.forEach(function(mutation) {
                    if (mutation.type !== 'attributes') return;
                    if (mutation.attributeName !== 'src') return;

                    var img    = mutation.target;
                    var parent = img.parentElement;
                    if (!parent) return;

                    var inCoverDiv = COVER_IDS.some(function(id) {
                        return parent.id === id;
                    });
                    if (!inCoverDiv) return;

                    var newSrc = img.getAttribute('src');

                    if (isBadged(newSrc)) {
                        lastAppliedUrl = newSrc;
                    } else {
                        if (lastAppliedUrl) {
                            img.src = lastAppliedUrl;
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
        }
        tryInstall();
    }

    // ── MPD.json interceptor ──────────────────────────────────────────────────
    function installMpdInterceptor() {
        function tryInstall() {
            if (typeof MPD === 'undefined') { setTimeout(tryInstall, 200); return; }
            var _json = MPD.json || 0;
            Object.defineProperty(MPD, 'json', {
                get: function () { return _json; },
                set: function (val) {
                    _json = val;
                    if (sseActive && lastAppliedUrl && val && typeof val === 'object') {
                        val.coverurl = lastAppliedUrl;
                    }
                },
                configurable: true
            });
        }
        tryInstall();
    }

    // ── SSE connection ────────────────────────────────────────────────────────
    function initSSE() {
        var evtSource = new EventSource(
            'http://' + window.location.hostname + ':5000/cover-events');

        evtSource.onopen = function () {
            sseActive = true;
            if (lastAppliedUrl) {
                pendingUrl = lastAppliedUrl;
                scheduleApply();
            }
        };

        evtSource.onmessage = function (e) {
            try {
                var data = JSON.parse(e.data);
                if ((data.event === 'cover_updated' || data.event === 'logo_restored') &&
                        data.cover_url) {
                    sseActive = true;
                    enqueueCoverUpdate(data.cover_url);
                }
            } catch (_) {}
        };

        evtSource.onerror = function () {
            sseActive = false;
            evtSource.close();
            setTimeout(initSSE, 5000);
        };
    }

    // ── Boot ──────────────────────────────────────────────────────────────────
    installJqueryHtmlIntercept();
    installMutationGuard();
    installMpdInterceptor();

    console.log('[SSE] moode-sse-patch v6 loaded');
    initSSE();

})();
