/* moode-sse-patch V9 — Native jQuery DOM (Vanilla Parity, No CSS Override)
 *
 * Tested on: moOde Audio Player 10.2.4
 * Status:    STABLE — production ready
 *
 * Architecture decision:
 * Previous versions (V7, V8) used a CSS override approach injecting a <style>
 * tag with `content: url()` on multiple elements simultaneously. This caused
 * the vc4 HVS (Hardware Video Scaler) driver on Raspberry Pi 4 to crash
 * (kernel panic: __vc4_hvs_stop_channel) after sustained use.
 *
 * V9 uses the same jQuery .html() pattern that moOde uses natively for NAS
 * album art, making our SSE updates invisible to the GPU compositor.
 *
 * The brief black flash between cover transitions is intentional and matches
 * native moOde behavior — attempts to suppress it via CSS were a contributing
 * factor in the GPU crashes and have been permanently removed.
 */
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
            if (url === currentCoverUrl) return; // Idempotency guard
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
                    // Invalidate state, let moOde restore its native default
                    currentCoverUrl = '';
                }
            } catch (err) {}
        };

        evtSource.onerror = function() {
            // Silent resilience: cover stays on screen during reconnection
            console.log('[SSE] v9: connection error, retrying silently...');
        };

        // MutationObserver: if moOde natively changes the cover (e.g. NAS track
        // zapping), we yield control by invalidating our state without touching DOM
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
        console.log('[SSE] moode-sse-patch v9 loaded — moOde 10.2.4');

    });

})();
