// Drag-to-stretch zoom for the bill progression timeline.
//
// Zoom multiplies the horizontal density (px per day). The canvas grows
// WIDER when zoomed in — no cards are ever hidden, you just scroll the wrap
// horizontally to reach them. Zoom is purely visual (doesn't touch the
// date-range filter).
//
// Interactions:
//   - Drag horizontally on an empty area of the timeline chart → zoom so the
//     selected x-range fills the viewport width, scroll-center on it.
//   - Double-click on empty timeline area → reset to 100%.
//   - Ctrl + mousewheel → zoom around the cursor position.
//
// Everything the user sees (cards, axis dots, connectors, tick marks, tick
// labels) has its `left` stored once as `data-base-left` on first zoom
// interaction and re-derived as `baseLeft * zoomFactor` on every gesture.

(function () {
    function canvas() { return document.querySelector('.timeline-canvas'); }
    function wrap()   { return document.querySelector('.timeline-wrap'); }

    const ZOOMABLE = '.bill-card, .timeline-dot, .timeline-connector, ' +
                     '.timeline-tick, .timeline-tick-label';

    // Row top positions — must match ROWS in components/timeline.py.
    // Order is important: packing walks this list and places each card in the
    // first row where it doesn't collide.
    const ROWS_Y = [272, 400, 162, 510, 52, 620, 730, 840];
    const CARD_W = 188;
    const CARD_H = 96;
    const AXIS_Y = 380;
    const MIN_GAP = CARD_W + 10;

    // Re-assigns rows for all currently-visible cards so they pack tightly
    // against the axis. Also updates each card's matching axis dot + connector
    // line so the vertical drop still lands on the moved card.
    function repack() {
        const c = canvas();
        if (!c) return;
        // Collect visible cards (legend hides via display:none or data-hidden).
        const cards = [...c.querySelectorAll('.bill-card')]
            .filter(el => el.style.display !== 'none');
        cards.sort((a, b) => parseFloat(a.style.left) - parseFloat(b.style.left));
        const rowLastX = new Array(ROWS_Y.length).fill(-10000);
        const cardRowByBillEvent = {};
        for (const card of cards) {
            const left = parseFloat(card.style.left);
            const centerX = left + CARD_W / 2;
            let chosen = -1;
            for (let i = 0; i < rowLastX.length; i++) {
                if (centerX - rowLastX[i] >= MIN_GAP) { chosen = i; break; }
            }
            if (chosen < 0) {
                // All rows collide — pick the one with the oldest last-placed x
                let minX = Infinity, minI = 0;
                for (let i = 0; i < rowLastX.length; i++) {
                    if (rowLastX[i] < minX) { minX = rowLastX[i]; minI = i; }
                }
                chosen = minI;
            }
            rowLastX[chosen] = centerX;
            const rowY = ROWS_Y[chosen];
            card.style.top = rowY + 'px';
            const key = (card.getAttribute('data-bill-id') || '') + '|' +
                        (card.getAttribute('data-event-date') || '');
            cardRowByBillEvent[key] = {rowY, centerX};
        }

        // Update every connector so it drops from its card's (new) row to the axis.
        c.querySelectorAll('.timeline-connector').forEach(cn => {
            const key = (cn.getAttribute('data-bill-id') || '') + '|' +
                        (cn.getAttribute('data-event-date') || '');
            const info = cardRowByBillEvent[key];
            if (!info) {
                cn.style.display = 'none';
                return;
            }
            cn.style.display = '';
            cn.style.left = info.centerX + 'px';
            const cardBottom = info.rowY + CARD_H;
            if (info.rowY < AXIS_Y) {
                cn.style.top = cardBottom + 'px';
                cn.style.height = Math.max(0, AXIS_Y - cardBottom) + 'px';
            } else {
                cn.style.top = AXIS_Y + 'px';
                cn.style.height = Math.max(0, info.rowY - AXIS_Y) + 'px';
            }
        });
    }

    // Publish on window so callbacks/timeline.py clientside code can trigger a
    // repack after legend hide/show.
    window.repackTimeline = repack;

    // We snapshot the CENTER x of every zoomable element (not the bounding-box
    // left). That way each element stays centered on the same canvas x across
    // zoom levels regardless of how wide the element itself is. Cards (188 px)
    // would otherwise drift away from their axis dots as the canvas stretches.
    function snapshotIfNeeded() {
        const c = canvas();
        if (!c) return false;
        if (!c.dataset.baseW) c.dataset.baseW = String(c.offsetWidth);
        c.querySelectorAll(ZOOMABLE).forEach(el => {
            if (!el.dataset.baseCx) {
                const left = parseFloat(el.style.left);
                if (isNaN(left)) return;
                const halfW = el.classList.contains('bill-card') ? CARD_W / 2 : 0;
                el.dataset.baseCx = String(left + halfW);
            }
        });
        return true;
    }

    function getFactor() {
        return parseFloat((canvas() && canvas().dataset.zoomFactor) || '1');
    }

    function setFactor(factor, pivotViewportX) {
        const c = canvas();
        const w = wrap();
        if (!c || !w) return;
        if (!snapshotIfNeeded()) return;
        const prevFactor = getFactor();
        const baseW = parseFloat(c.dataset.baseW);
        // Zoom-out is capped at viewport-fit so the whole filtered timeline
        // is always visible at max zoom-out (never shrinks below viewport).
        const viewportW = w.clientWidth;
        const minFactor = Math.min(1, viewportW / baseW);
        factor = Math.max(minFactor, Math.min(12, factor));

        // Keep the pivot point (cursor or drag midpoint) stable on screen.
        let pivotCanvasX = null;
        if (pivotViewportX != null) {
            pivotCanvasX = w.scrollLeft + pivotViewportX;
        }

        c.style.width = (baseW * factor) + 'px';
        c.querySelectorAll(ZOOMABLE).forEach(el => {
            const cx = parseFloat(el.dataset.baseCx);
            if (isNaN(cx)) return;
            const scaledCx = cx * factor;
            const halfW = el.classList.contains('bill-card') ? CARD_W / 2 : 0;
            el.style.left = (scaledCx - halfW) + 'px';
        });
        c.dataset.zoomFactor = String(factor);

        if (pivotCanvasX != null && prevFactor > 0) {
            const baseCanvasX = pivotCanvasX / prevFactor;
            const newPivotCanvasX = baseCanvasX * factor;
            w.scrollLeft = newPivotCanvasX - pivotViewportX;
        }
        repack();
    }

    function reset() {
        const c = canvas();
        const w = wrap();
        if (!c || !w) return;
        if (!snapshotIfNeeded()) return;
        const baseW = parseFloat(c.dataset.baseW);
        c.style.width = baseW + 'px';
        c.querySelectorAll(ZOOMABLE).forEach(el => {
            const cx = parseFloat(el.dataset.baseCx);
            if (isNaN(cx)) return;
            const halfW = el.classList.contains('bill-card') ? CARD_W / 2 : 0;
            el.style.left = (cx - halfW) + 'px';
        });
        c.dataset.zoomFactor = '1';
        w.scrollLeft = 0;
        repack();
    }

    // ------------------------------------------------------------------
    // Gestures
    // ------------------------------------------------------------------
    function isScrollbarClick(e) {
        const w = wrap();
        if (!w) return false;
        const r = w.getBoundingClientRect();
        // native scrollbars sit inside the wrap's padding box. If the click
        // is below the last scrollable row or right of the scrollable area
        // the browser already prevents bubbling into children. But horizontal
        // scrollbar clicks with e.target === wrap can reach us. Filter by
        // comparing client coordinates to the wrap's CLIENT area.
        const bottomScrollbarStartY = r.top + w.clientHeight;
        const rightScrollbarStartX = r.left + w.clientWidth;
        if (e.clientY >= bottomScrollbarStartY) return true;
        if (e.clientX >= rightScrollbarStartX) return true;
        return false;
    }

    function isInsideCanvas(e) {
        const c = canvas();
        return c && c.contains(e.target);
    }

    let dragStartX = null;
    let dragStartScroll = 0;
    let selectRect = null;

    function onMouseDown(e) {
        if (e.button !== 0) return;
        if (isScrollbarClick(e)) return;
        if (!isInsideCanvas(e)) return;
        if (e.target.closest('.bill-card, button, a, input, .rc-slider')) return;
        const w = wrap();
        const r = w.getBoundingClientRect();
        dragStartX = e.clientX - r.left;
        dragStartScroll = w.scrollLeft;
        w.classList.add('drag-active');
    }

    function onMouseMove(e) {
        if (dragStartX == null) return;
        const w = wrap();
        const r = w.getBoundingClientRect();
        const x = e.clientX - r.left;
        const lo = Math.min(dragStartX, x);
        const hi = Math.max(dragStartX, x);
        if (hi - lo < 3) return;
        if (!selectRect) {
            selectRect = document.createElement('div');
            selectRect.className = 'zoom-select-rect';
            w.appendChild(selectRect);
        }
        selectRect.style.left = (w.scrollLeft + lo) + 'px';
        selectRect.style.width = (hi - lo) + 'px';
    }

    function onMouseUp(e) {
        if (dragStartX == null) return;
        const w = wrap();
        const r = w.getBoundingClientRect();
        const x = e.clientX - r.left;
        w.classList.remove('drag-active');
        const dist = Math.abs(x - dragStartX);
        if (dist > 10) {
            // Stretch so the selected range fills the viewport.
            const viewportW = w.clientWidth;
            const selectionW = dist;
            const relMult = viewportW / selectionW;
            const curFactor = getFactor();
            const targetFactor = Math.min(12, curFactor * relMult);
            // pivot: midpoint of the drag in viewport coords
            const pivotX = Math.min(dragStartX, x) + dist / 2;
            setFactor(targetFactor, pivotX);
        }
        if (selectRect && selectRect.parentElement) {
            selectRect.parentElement.removeChild(selectRect);
        }
        selectRect = null;
        dragStartX = null;
    }

    function onDblClick(e) {
        if (!isInsideCanvas(e)) return;
        if (e.target.closest('.bill-card, button, a, input, .rc-slider')) return;
        reset();
    }

    function onWheel(e) {
        if (!(e.ctrlKey || e.metaKey)) return;
        if (!isInsideCanvas(e)) return;
        e.preventDefault();
        const w = wrap();
        const r = w.getBoundingClientRect();
        const pivot = e.clientX - r.left;
        const factor = getFactor();
        const next = e.deltaY < 0 ? factor * 1.2 : factor / 1.2;
        setFactor(next, pivot);
    }

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
