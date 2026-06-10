/* moode-sse-patch V7.5 */

;(function () {
    'use strict';

    var lastEventTs    = 0;
    var lastAppliedUrl = null;
    var rafPending     = false;
    var sseActive      = false;
    var pendingUrl     = null;

    var COVER_IDS = ['coverart-url', 'playbar-cover', 'cover-backdrop',
                     'ss-backdrop',  'ss-coverart-url'];

    function extractTs(url) {
        var m = url && url.match(/[?&]t=(\d+)/);
        return m ? parseInt(m[1], 10) : 0;
    }

    function isBadged(url) {
        return url && url.indexOf('?t=') !== -1;
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
        requestAnimationFrame(applyPendingUrl);
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
            };
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
                        if (oldSrc.indexOf('/coverart.php/') !== 0) return;
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
                        if (!sseActive) return;

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
                            if (lastAppliedUrl) img.src = lastAppliedUrl;
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
                    if (val && typeof val === 'object') console.log('[SSE] MPD.json set file=' + val.file + ' coverurl=' + (val.coverurl||'').substring(0,60));
                    if (val && typeof val === 'object' && val.coverurl &&
                            val.coverurl.indexOf('/coverart.php/') === 0) {
                        sseActive      = false;
                        lastAppliedUrl = null;
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
        var evtSource = new EventSource('/cover-events');

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
                if (data.event === 'cover_updated' && data.cover_url) {
                    sseActive = true;
                    enqueueCoverUpdate(data.cover_url);
                } else if (data.event === 'logo_restored' && data.cover_url) {
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

    installJqueryHtmlIntercept();
    installMutationGuard();
    installMpdInterceptor();
    window._sseDebug = function () {
        return { sseActive: sseActive, lastAppliedUrl: lastAppliedUrl, pendingUrl: pendingUrl };
    };
    console.log('[SSE] moode-sse-patch v7.5 loaded');
    initSSE();

})();
