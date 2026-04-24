// Pan + zoom for the timeline — CSS `zoom` (reflows layout, crisp text) for
// scale; native scrollLeft/scrollTop for pan. No server round-trip.

(function () {
    const MIN_SCALE = 0.3;
    const MAX_SCALE = 3.0;
    const WHEEL_STEP = 1.1;
    const BUTTON_STEP = 1.25;

    function canvas() { return document.querySelector('.timeline-canvas'); }
    function wrap()   { return document.querySelector('.timeline-wrap'); }

    function state() {
        if (!window.__tlZoom) window.__tlZoom = {scale: 1.0};
        return window.__tlZoom;
    }

    function applyScale() {
        const c = canvas();
        if (!c) return;
        c.style.zoom = state().scale;
    }

    function setScaleAround(newScale, clientX, clientY) {
        newScale = Math.max(MIN_SCALE, Math.min(MAX_SCALE, newScale));
        const w = wrap(); if (!w) return;
        const old = state().scale;
        // Where in the (scaled) canvas is the cursor now?
        const r = w.getBoundingClientRect();
        const cursorXinWrap = clientX - r.left;
        const cursorYinWrap = clientY - r.top;
        const prevScrollX = w.scrollLeft;
        const prevScrollY = w.scrollTop;
        // Natural (pre-zoom) coordinate under the cursor.
        const natX = (prevScrollX + cursorXinWrap) / old;
        const natY = (prevScrollY + cursorYinWrap) / old;
        state().scale = newScale;
        applyScale();
        // Re-scroll so the same natural point sits under the cursor at the new scale.
        w.scrollLeft = natX * newScale - cursorXinWrap;
        w.scrollTop  = natY * newScale - cursorYinWrap;
    }

    function reset() {
        state().scale = 1;
        applyScale();
        const w = wrap(); if (w) { w.scrollLeft = 0; w.scrollTop = 0; }
    }

    function fitAll() {
        const w = wrap(); const c = canvas();
        if (!w || !c) return;
        const cards = [...c.querySelectorAll('.bill-card')];
        if (!cards.length) return reset();
        const CARD_W = 188;
        let minX = Infinity, maxX = -Infinity;
        cards.forEach(el => {
            const left = parseFloat(el.style.left);
            if (isNaN(left)) return;
            minX = Math.min(minX, left);
            maxX = Math.max(maxX, left + CARD_W);
        });
        if (!isFinite(minX)) return reset();
        const contentW = maxX - minX;
        const targetScale = Math.min(MAX_SCALE, Math.max(MIN_SCALE,
            (w.clientWidth - 40) / contentW));
        state().scale = targetScale;
        applyScale();
        w.scrollLeft = (minX * targetScale) - 20;  // small left padding
        w.scrollTop = 0;
    }

    // ------------------------------------------------------------------
    // Pan — click-drag on empty canvas, drive scrollLeft/Top directly.
    // ------------------------------------------------------------------
    let panStart = null;

    function isScrollbarClick(e) {
        const w = wrap();
        if (!w) return false;
        const r = w.getBoundingClientRect();
        if (e.clientY >= r.top + w.clientHeight) return true;
        if (e.clientX >= r.left + w.clientWidth) return true;
        return false;
    }

    function isInsideCanvas(e) {
        const c = canvas();
        return c && c.contains(e.target);
    }

    function onMouseDown(e) {
        if (e.button !== 0) return;
        if (isScrollbarClick(e)) return;
        if (!isInsideCanvas(e)) return;
        if (e.target.closest('.bill-card, button, a, input, .rc-slider')) return;
        const w = wrap();
        panStart = {x: e.clientX, y: e.clientY,
                    sl: w.scrollLeft, st: w.scrollTop};
        w.classList.add('drag-active');
        e.preventDefault();
    }

    function onMouseMove(e) {
        if (!panStart) return;
        const w = wrap();
        w.scrollLeft = panStart.sl - (e.clientX - panStart.x);
        w.scrollTop  = panStart.st - (e.clientY - panStart.y);
    }

    function onMouseUp() {
        if (!panStart) return;
        panStart = null;
        const w = wrap(); if (w) w.classList.remove('drag-active');
    }

    function onWheel(e) {
        if (!(e.ctrlKey || e.metaKey)) return;
        if (!isInsideCanvas(e)) return;
        e.preventDefault();
        const next = e.deltaY < 0 ? state().scale * WHEEL_STEP
                                  : state().scale / WHEEL_STEP;
        setScaleAround(next, e.clientX, e.clientY);
    }

    function zoomStep(factor) {
        const w = wrap(); if (!w) return;
        const r = w.getBoundingClientRect();
        setScaleAround(state().scale * factor,
                       r.left + w.clientWidth / 2,
                       r.top + w.clientHeight / 2);
    }

    function onDblClick(e) {
        if (!isInsideCanvas(e)) return;
        if (e.target.closest('.bill-card, button, a, input, .rc-slider')) return;
        fitAll();
    }

    function install() {
        if (window.__timelineZoomBound) return;
        window.__timelineZoomBound = true;
        document.addEventListener('mousedown', onMouseDown);
        document.addEventListener('mousemove', onMouseMove);
        document.addEventListener('mouseup', onMouseUp);
        document.addEventListener('dblclick', onDblClick);
        document.addEventListener('wheel', onWheel, {passive: false});
        document.addEventListener('click', (e) => {
            if (e.target.closest('#timeline-reset-btn'))   { e.preventDefault(); return reset(); }
            if (e.target.closest('#timeline-zoom-in-btn'))  { e.preventDefault(); return zoomStep(BUTTON_STEP); }
            if (e.target.closest('#timeline-zoom-out-btn')) { e.preventDefault(); return zoomStep(1 / BUTTON_STEP); }
        });
        // Re-apply zoom when Dash re-renders the canvas (filter/hide changes).
        new MutationObserver(() => applyScale())
            .observe(document.body, {childList: true, subtree: true});
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', install);
    } else {
        install();
    }
})();
