/* moode-sse-patch V9 — Native jQuery DOM (Vanilla Parity, No CSS Override) */
;(function () {
    'use strict';

    function waitForJQuery(cb) {
        if (window.jQuery) { cb(window.jQuery); }
        else { setTimeout(function() { waitForJQuery(cb); }, 100); }
    }

    waitForJQuery(function($) {

        var currentCoverUrl = '';
        var DEFAULT_COVER = '/images/default-cover-v6.svg';

        function applyNativeCover(url) {
            var src = url || DEFAULT_COVER;
            $('#coverart-url').html('<img class="coverart" src="' + src + '" alt="Cover art not found">');
            $('#playbar-cover').html('<img src="' + src + '">');
            $('#ss-coverart-url').html($('#coverart-url').html());
        }

        function preloadAndApply(url) {
            if (url === currentCoverUrl) return;
            currentCoverUrl = url;
            var img = new Image();
            img.onload = function() { if (currentCoverUrl === url) applyNativeCover(url); };
            img.onerror = function() { if (currentCoverUrl === url) { currentCoverUrl = ''; applyNativeCover(''); } };
            img.src = url;
        }

        var evtSource = new EventSource('http://' + window.location.hostname + ':5000/cover-events');

        evtSource.onmessage = function(e) {
            try {
                var data = JSON.parse(e.data);
                if (data.event === 'cover_updated' && data.cover_url) {
                    preloadAndApply(data.cover_url);
                } else if (data.event === 'logo_restored' && currentCoverUrl !== '') {
                    currentCoverUrl = '';
                }
            } catch (err) {}
        };

        evtSource.onerror = function() {
            console.log('[SSE] v9: connection error, retrying silently...');
        };

        function setupObserver() {
            var moodeCover = document.querySelector('#coverart-url img');
            if (moodeCover) {
                new MutationObserver(function() {
                    var src = moodeCover.getAttribute('src');
                    if (src && src !== currentCoverUrl && !src.includes('default-cover')) {
                        currentCoverUrl = '';
                    }
                }).observe(moodeCover, { attributes: true, attributeFilter: ['src'] });
                console.log('[SSE] moode-sse-patch v9: observer attached');
            } else {
                setTimeout(setupObserver, 500);
            }
        }

        setupObserver();
        console.log('[SSE] moode-sse-patch v9 loaded');

    });

})();
