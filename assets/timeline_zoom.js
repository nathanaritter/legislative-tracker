// Drag-to-zoom on the bill progression timeline.
//
// Server-side render positions every card, axis dot, and connector at the
// correct pixel for the FULL data span. This JS only reacts to explicit user
// gestures (drag, Ctrl+wheel, double-click) — no MutationObserver that could
// loop against Dash's own DOM writes.
//
// Interactions:
//   - Mousedown + horizontal drag on empty timeline area → zoom into that
//     horizontal range on release.
//   - Double-click on the timeline → reset to full span.
//   - Ctrl + mousewheel → zoom around cursor.

(function () {
    const CARD_W = 188;

    function msFrom(dateStr) {
        const [y, m, d] = dateStr.split('-').map(Number);
        return Date.UTC(y, (m || 1) - 1, d || 1);
    }

    function getBounds() {
        const el = document.querySelector('#timeline-bounds');
        if (!el) return null;
        return {
            dMin: msFrom(el.getAttribute('data-d-min')),
            dMax: msFrom(el.getAttribute('data-d-max')),
            margin: parseInt(el.getAttribute('data-margin') || '0', 10),
        };
    }

    function getZoom() {
        const b = getBounds();
        if (!b) return null;
        if (!window._timelineZoom) {
            window._timelineZoom = {visibleMin: b.dMin, visibleMax: b.dMax};
        }
        return window._timelineZoom;
    }

    function applyZoom() {
        const b = getBounds();
        if (!b) return;
        const z = getZoom();
        if (!z) return;
        const wrap = document.querySelector('.timeline-wrap');
        if (!wrap) return;

        const viewportW = wrap.clientWidth;
        const usable = viewportW - 2 * b.margin;
        const visSpan = Math.max(1, z.visibleMax - z.visibleMin);

        document.querySelectorAll('.bill-card, .timeline-dot, .timeline-connector').forEach(el => {
            const ds = el.getAttribute('data-event-date');
            if (!ds) return;
            const ms = msFrom(ds);
            const outside = ms < z.visibleMin || ms > z.visibleMax;
            el.style.display = outside ? 'none' : '';
            if (outside) return;
            const frac = (ms - z.visibleMin) / visSpan;
            const centerX = b.margin + frac * usable;
            if (el.classList.contains('bill-card')) {
                el.style.left = (centerX - CARD_W / 2) + 'px';
            } else {
                el.style.left = centerX + 'px';
            }
        });

        const axis = document.querySelector('.timeline-axis');
        if (axis) {
            axis.style.left = b.margin + 'px';
            axis.style.right = b.margin + 'px';
        }
    }

    function setZoom(visibleMin, visibleMax) {
        const b = getBounds();
        if (!b) return;
        const minSpan = 7 * 86400000;
        visibleMin = Math.max(b.dMin, visibleMin);
        visibleMax = Math.min(b.dMax, visibleMax);
        if (visibleMax - visibleMin < minSpan) {
            const mid = (visibleMax + visibleMin) / 2;
            visibleMin = Math.max(b.dMin, mid - minSpan / 2);
            visibleMax = Math.min(b.dMax, mid + minSpan / 2);
        }
        window._timelineZoom = {visibleMin, visibleMax};
        applyZoom();
    }

    function resetZoom() {
        const b = getBounds();
        if (!b) return;
        window._timelineZoom = {visibleMin: b.dMin, visibleMax: b.dMax};
        applyZoom();
    }

    // --- Drag selection --------------------------------------------------
    let dragStartX = null;
    let selectRect = null;

    function onMouseDown(e) {
        if (e.target.closest('.bill-card, button, a, input, .rc-slider')) return;
        if (e.button !== 0) return;
        const wrap = document.querySelector('.timeline-wrap');
        if (!wrap || !wrap.contains(e.target)) return;
        const rect = wrap.getBoundingClientRect();
        dragStartX = e.clientX - rect.left;
        wrap.classList.add('drag-active');
    }

    function onMouseMove(e) {
        if (dragStartX == null) return;
        const wrap = document.querySelector('.timeline-wrap');
        if (!wrap) return;
        const rect = wrap.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const lo = Math.min(dragStartX, x);
        const hi = Math.max(dragStartX, x);
        if (hi - lo < 3) return;
        if (!selectRect) {
            selectRect = document.createElement('div');
            selectRect.className = 'zoom-select-rect';
            wrap.appendChild(selectRect);
        }
        selectRect.style.left = lo + 'px';
        selectRect.style.width = (hi - lo) + 'px';
    }

    function onMouseUp(e) {
        if (dragStartX == null) return;
        const wrap = document.querySelector('.timeline-wrap');
        const rect = wrap ? wrap.getBoundingClientRect() : null;
        const x = rect ? e.clientX - rect.left : dragStartX;
        wrap && wrap.classList.remove('drag-active');
        const b = getBounds();
        if (b && rect && Math.abs(x - dragStartX) > 5) {
            const z = getZoom();
            const usable = wrap.clientWidth - 2 * b.margin;
            const visSpan = z.visibleMax - z.visibleMin;
            const pxToMs = (px) => z.visibleMin + ((px - b.margin) / usable) * visSpan;
            const lo = Math.min(dragStartX, x);
            const hi = Math.max(dragStartX, x);
            setZoom(pxToMs(lo), pxToMs(hi));
        }
        if (selectRect && selectRect.parentElement) {
            selectRect.parentElement.removeChild(selectRect);
        }
        selectRect = null;
        dragStartX = null;
    }

    function onDblClick(e) {
        if (e.target.closest('.bill-card, button, a, input, .rc-slider')) return;
        const wrap = document.querySelector('.timeline-wrap');
        if (wrap && wrap.contains(e.target)) resetZoom();
    }

    function onWheel(e) {
        if (!e.ctrlKey && !e.metaKey) return;
        const wrap = document.querySelector('.timeline-wrap');
        if (!wrap || !wrap.contains(e.target)) return;
        e.preventDefault();
        const b = getBounds();
        if (!b) return;
        const rect = wrap.getBoundingClientRect();
        const cursorX = e.clientX - rect.left;
        const usable = wrap.clientWidth - 2 * b.margin;
        const z = getZoom();
        const visSpan = z.visibleMax - z.visibleMin;
        const cursorMs = z.visibleMin + ((cursorX - b.margin) / usable) * visSpan;
        const scale = e.deltaY < 0 ? 0.8 : 1.25;
        const newSpan = visSpan * scale;
        const leftFrac = (cursorMs - z.visibleMin) / visSpan;
        const newMin = cursorMs - newSpan * leftFrac;
        setZoom(newMin, newMin + newSpan);
    }

    // Install listeners once on document. They use live DOM queries so they
    // work regardless of when Dash renders the timeline-wrap.
    function install() {
        if (window.__timelineZoomBound) return;
        window.__timelineZoomBound = true;
        document.addEventListener('mousedown', onMouseDown);
        document.addEventListener('mousemove', onMouseMove);
        document.addEventListener('mouseup', onMouseUp);
        document.addEventListener('dblclick', onDblClick);
        document.addEventListener('wheel', onWheel, {passive: false});
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', install);
    } else {
        install();
    }
})();
