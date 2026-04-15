// Clientside drag-to-zoom for the bill progression timeline.
//
// State lives entirely in `window._timelineZoom` — never round-trips to Python.
// Zoom is PURELY VISUAL: it changes which portion of the loaded event span is
// mapped to the viewport width. The sidebar date-range filter (which controls
// what data is LOADED) is unaffected.
//
// Interactions:
//   - Mousedown + horizontal drag on empty timeline area → select a range and
//     zoom into it on release.
//   - Double-click on the timeline → reset to full span.
//   - Ctrl + mousewheel on the timeline → zoom in/out around the cursor.
//
// Every card, axis dot, and connector carries a `data-event-date` attribute
// (ISO YYYY-MM-DD). On any zoom change the JS iterates those elements and
// rewrites their CSS `left` based on the current visible window.

(function () {
    const CARD_W = 188;

    function msFrom(dateStr) {
        // Parse ISO date as UTC midnight so day arithmetic is exact.
        const [y, m, d] = dateStr.split('-').map(Number);
        return Date.UTC(y, (m || 1) - 1, d || 1);
    }

    function fmtISO(ms) {
        const d = new Date(ms);
        const yyyy = d.getUTCFullYear();
        const mm = String(d.getUTCMonth() + 1).padStart(2, '0');
        const dd = String(d.getUTCDate()).padStart(2, '0');
        return `${yyyy}-${mm}-${dd}`;
    }

    function getBounds() {
        const el = document.querySelector('#timeline-bounds');
        if (!el) return null;
        return {
            dMin: msFrom(el.getAttribute('data-d-min')),
            dMax: msFrom(el.getAttribute('data-d-max')),
            margin: parseInt(el.getAttribute('data-margin') || '0', 10),
            canvasW: parseInt(el.getAttribute('data-canvas-w') || '1400', 10),
        };
    }

    function getZoom() {
        if (!window._timelineZoom) {
            const b = getBounds();
            window._timelineZoom = b ? {visibleMin: b.dMin, visibleMax: b.dMax} : null;
        }
        return window._timelineZoom;
    }

    function setZoom(visibleMin, visibleMax) {
        const b = getBounds();
        if (!b) return;
        // Clamp to data bounds + minimum span of 7 days.
        const minSpan = 7 * 86400000;
        visibleMin = Math.max(b.dMin, visibleMin);
        visibleMax = Math.min(b.dMax, visibleMax);
        if (visibleMax - visibleMin < minSpan) {
            const mid = (visibleMax + visibleMin) / 2;
            visibleMin = mid - minSpan / 2;
            visibleMax = mid + minSpan / 2;
            visibleMin = Math.max(b.dMin, visibleMin);
            visibleMax = Math.min(b.dMax, visibleMax);
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

    function applyZoom() {
        const b = getBounds();
        const z = getZoom();
        if (!b || !z) return;
        const wrap = document.querySelector('.timeline-wrap');
        if (!wrap) return;
        const viewportW = wrap.clientWidth;
        const usable = viewportW - 2 * b.margin;
        const visSpan = Math.max(1, z.visibleMax - z.visibleMin);

        function px(eventMs) {
            const frac = (eventMs - z.visibleMin) / visSpan;
            return b.margin + frac * usable;
        }

        // Card + dot + connector positioning
        document.querySelectorAll('.bill-card, .timeline-dot, .timeline-connector').forEach(el => {
            const ds = el.getAttribute('data-event-date');
            if (!ds) return;
            const ms = msFrom(ds);
            // Hide elements outside the visible window
            const outside = ms < z.visibleMin || ms > z.visibleMax;
            // Preserve existing display:none from the bill-hidden toggle
            const billHidden = el.dataset.billHiddenByUser === '1';
            el.style.display = (outside || billHidden) ? 'none' : '';
            if (outside) return;
            const centerX = px(ms);
            if (el.classList.contains('bill-card')) {
                el.style.left = (centerX - CARD_W / 2) + 'px';
            } else {
                el.style.left = centerX + 'px';
            }
        });

        // Axis line
        const axis = document.querySelector('.timeline-axis');
        if (axis) {
            axis.style.left = b.margin + 'px';
            axis.style.right = b.margin + 'px';
        }

        // Tick labels (year + month) — redrawn dynamically for current visible range
        redrawTicks(b, z, usable);
    }

    function redrawTicks(b, z, usable) {
        const canvas = document.querySelector('.timeline-canvas');
        if (!canvas) return;
        canvas.querySelectorAll('.timeline-tick, .timeline-tick-label').forEach(el => el.remove());

        const visSpan = z.visibleMax - z.visibleMin;
        const spanDays = visSpan / 86400000;
        const spanYears = spanDays / 365;
        const showMonths = spanYears <= 3;

        const dMin = new Date(z.visibleMin);
        const dMax = new Date(z.visibleMax);

        // Year ticks
        for (let y = dMin.getUTCFullYear(); y <= dMax.getUTCFullYear() + 1; y++) {
            const ms = Date.UTC(y, 0, 1);
            if (ms < z.visibleMin || ms > z.visibleMax) continue;
            const x = b.margin + ((ms - z.visibleMin) / visSpan) * usable;
            addTick(canvas, x, String(y), true);
        }
        // Month ticks
        if (showMonths) {
            for (let y = dMin.getUTCFullYear(); y <= dMax.getUTCFullYear(); y++) {
                for (let m = 0; m < 12; m++) {
                    if (m === 0) continue;
                    const ms = Date.UTC(y, m, 1);
                    if (ms < z.visibleMin || ms > z.visibleMax) continue;
                    const x = b.margin + ((ms - z.visibleMin) / visSpan) * usable;
                    const label = new Date(ms).toLocaleString('en-US', {month: 'short', timeZone: 'UTC'});
                    addTick(canvas, x, label, false);
                }
            }
        }
    }

    function addTick(canvas, x, label, isMajor) {
        const tick = document.createElement('div');
        tick.className = 'timeline-tick';
        tick.style.left = x + 'px';
        tick.style.top = isMajor ? '272px' : '276px';
        tick.style.height = isMajor ? '18px' : '10px';
        canvas.appendChild(tick);

        const lbl = document.createElement('div');
        lbl.className = 'timeline-tick-label';
        lbl.style.left = x + 'px';
        lbl.style.fontSize = isMajor ? '11px' : '10px';
        lbl.style.fontWeight = isMajor ? '600' : '500';
        lbl.textContent = label;
        canvas.appendChild(lbl);
    }

    // ------------------------------------------------------------------
    // Drag interaction
    // ------------------------------------------------------------------
    let dragStartX = null;
    let dragStartTime = 0;
    let selectRect = null;

    function ensureSelectRect(wrap) {
        if (!selectRect) {
            selectRect = document.createElement('div');
            selectRect.className = 'zoom-select-rect';
            wrap.appendChild(selectRect);
        }
        return selectRect;
    }

    function onMouseDown(e) {
        // Ignore clicks on cards/legend/buttons — only drag on empty chart area
        if (e.target.closest('.bill-card, button, a, input, .rc-slider')) return;
        if (e.button !== 0) return;
        const wrap = e.currentTarget;
        const rect = wrap.getBoundingClientRect();
        dragStartX = e.clientX - rect.left;
        dragStartTime = Date.now();
        wrap.classList.add('drag-active');
    }

    function onMouseMove(e) {
        if (dragStartX == null) return;
        const wrap = e.currentTarget;
        const rect = wrap.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const lo = Math.min(dragStartX, x);
        const hi = Math.max(dragStartX, x);
        if (hi - lo < 3) return;
        const sr = ensureSelectRect(wrap);
        sr.style.left = lo + 'px';
        sr.style.width = (hi - lo) + 'px';
    }

    function onMouseUp(e) {
        if (dragStartX == null) return;
        const wrap = e.currentTarget;
        wrap.classList.remove('drag-active');
        const rect = wrap.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const dragPx = Math.abs(x - dragStartX);
        const b = getBounds();
        if (b && dragPx > 5) {
            // Convert pixel range to date range and zoom
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
        resetZoom();
    }

    function onWheel(e) {
        if (!e.ctrlKey && !e.metaKey) return;
        e.preventDefault();
        const b = getBounds();
        if (!b) return;
        const wrap = e.currentTarget;
        const rect = wrap.getBoundingClientRect();
        const cursorX = e.clientX - rect.left;
        const usable = wrap.clientWidth - 2 * b.margin;
        const z = getZoom();
        const visSpan = z.visibleMax - z.visibleMin;
        const cursorMs = z.visibleMin + ((cursorX - b.margin) / usable) * visSpan;
        const scale = e.deltaY < 0 ? 0.8 : 1.25;  // zoom in / out
        const newSpan = visSpan * scale;
        // Keep cursorMs stationary — pivot the window around it
        const leftFrac = (cursorMs - z.visibleMin) / visSpan;
        const newMin = cursorMs - newSpan * leftFrac;
        const newMax = newMin + newSpan;
        setZoom(newMin, newMax);
    }

    function bind() {
        const wrap = document.querySelector('.timeline-wrap');
        if (!wrap || wrap.__zoomBound) return;
        wrap.__zoomBound = true;
        wrap.addEventListener('mousedown', onMouseDown);
        wrap.addEventListener('mousemove', onMouseMove);
        window.addEventListener('mouseup', (e) => {
            if (dragStartX != null) onMouseUp.call({currentTarget: wrap}, e);
        });
        wrap.addEventListener('dblclick', onDblClick);
        wrap.addEventListener('wheel', onWheel, {passive: false});
    }

    function init() {
        bind();
        // Reset zoom to full span when bounds (data) change, then apply.
        const bounds = getBounds();
        if (bounds) {
            const z = window._timelineZoom;
            if (!z || z.visibleMin < bounds.dMin || z.visibleMax > bounds.dMax) {
                window._timelineZoom = {visibleMin: bounds.dMin, visibleMax: bounds.dMax};
            }
            applyZoom();
        }
    }

    // Watch for Dash re-renders of #timeline-bounds (the data-carrying div).
    // The bounds div is only replaced when the render callback produces new
    // children for #timeline-canvas — NOT when applyZoom rewrites individual
    // card `left` / `display` styles. That prevents the observer from re-
    // entering during zoom and avoids an infinite mutation loop.
    let rebindObserver = null;

    function hookCanvas() {
        const canvas = document.querySelector('#timeline-canvas');
        if (!canvas) return false;
        if (rebindObserver) rebindObserver.disconnect();
        rebindObserver = new MutationObserver((muts) => {
            for (const m of muts) {
                if (m.type === 'childList') {
                    // new render — reset zoom to full bounds
                    delete window._timelineZoom;
                    init();
                    return;
                }
            }
        });
        rebindObserver.observe(canvas, {childList: true});
        return true;
    }

    function start() {
        // Canvas may not exist yet on first page load — wait for it.
        if (!hookCanvas()) {
            const bodyObs = new MutationObserver(() => {
                if (hookCanvas()) bodyObs.disconnect();
            });
            bodyObs.observe(document.body, {childList: true, subtree: true});
        }
        init();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', start);
    } else {
        start();
    }
})();
