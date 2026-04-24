// Right-click context menu on bill cards + Reset View button wiring.
//
// The menu itself is a static DOM node declared in components/layout.py; this
// file positions it on contextmenu and writes hide choices to the Dash store
// via `dash_clientside.set_props`.

(function () {
    function menuEl()  { return document.getElementById('card-context-menu'); }
    function findCard(el) {
        while (el && el !== document.body) {
            if (el.classList && el.classList.contains('bill-card')) return el;
            el = el.parentElement;
        }
        return null;
    }

    function readStore() {
        // Dash stores are mirrored in `window.dash_clientside._dashprivate_*`
        // but that's not a public API. Instead, read via a hidden input hack:
        // we rely on set_props being one-way (write). The store's current value
        // lives in the Dash internal state; when we want to toggle, we always
        // compute the new state from the DOM snapshot + action, not from prior
        // store state. For that we keep a shadow copy updated whenever Dash
        // writes the store — via a MutationObserver on the store element isn't
        // viable, so we read through window.__hiddenStoreShadow set by a
        // small clientside_callback in callbacks/timeline.py. Fallback: {}.
        return window.__hiddenStoreShadow || {bills: [], cards: [], isolated: null};
    }

    function writeStore(bills, cards, isolated) {
        const data = {
            bills: Array.from(new Set(bills)).sort(),
            cards: Array.from(new Set(cards)).sort(),
            isolated: isolated || null,
        };
        window.__hiddenStoreShadow = data;
        if (window.dash_clientside && window.dash_clientside.set_props) {
            window.dash_clientside.set_props('hidden-bills-store', {data: data});
        }
    }

    // activeTarget is either a card DOM element (right-click context) OR a
    // synthetic object {billId, stage, isHidden, isIsolated} for legend-icon
    // clicks. Both shapes carry the data card_menu dispatch needs.
    let activeTarget = null;

    function configureMenuItems(target) {
        const m = menuEl();
        if (!m) return;
        const isHidden = !!target.isHidden;
        const isIsolated = !!target.isIsolated;
        const hasStage = !!target.stage;
        m.querySelectorAll('.cm-item').forEach(el => {
            const action = el.getAttribute('data-action');
            let show = true;
            if (action === 'hide-stage') show = hasStage && !isHidden;
            else if (action === 'hide-bill') show = !isHidden;
            else if (action === 'isolate-bill') show = true;
            else if (action === 'show-bill') show = isHidden || isIsolated;
            el.style.display = show ? '' : 'none';
            if (action === 'isolate-bill') {
                el.textContent = isIsolated ? 'Stop isolating this bill' : 'Isolate this bill';
            }
        });
    }

    function openMenu(e, target) {
        const m = menuEl();
        if (!m) return;
        activeTarget = target;
        configureMenuItems(target);
        m.classList.add('open');
        // Clamp to viewport.
        const mw = 220, mh = 150;
        const vw = window.innerWidth, vh = window.innerHeight;
        const x = Math.min(e.clientX, vw - mw - 8);
        const y = Math.min(e.clientY, vh - mh - 8);
        m.style.left = x + 'px';
        m.style.top  = y + 'px';
    }

    function closeMenu() {
        const m = menuEl();
        if (m) m.classList.remove('open');
        activeTarget = null;
    }

    function onContextMenu(e) {
        const card = findCard(e.target);
        if (!card) return;
        e.preventDefault();
        const state = readStore();
        const billId = card.getAttribute('data-bill-id');
        openMenu(e, {
            billId,
            stage: card.getAttribute('data-stage-group'),
            isHidden: (state.bills || []).includes(billId),
            isIsolated: state.isolated === billId,
        });
    }

    function onLegendIconClick(e) {
        const icon = e.target.closest('.legend-hide-icon');
        if (!icon) return;
        const billId = icon.getAttribute('data-bill-id');
        if (!billId) return;
        e.preventDefault();
        e.stopPropagation();
        openMenu(e, {
            billId,
            stage: null,   // legend icon scope is the whole bill
            isHidden: icon.getAttribute('data-is-hidden') === '1',
            isIsolated: icon.getAttribute('data-is-isolated') === '1',
        });
    }

    function onMenuClick(e) {
        const item = e.target.closest('.cm-item');
        if (!item || !activeTarget) return closeMenu();
        const action = item.getAttribute('data-action');
        const billId = activeTarget.billId;
        const stage  = activeTarget.stage;
        if (!billId) return closeMenu();

        const state = readStore();
        const bills = new Set(state.bills || []);
        const cards = new Set(state.cards || []);
        let isolated = state.isolated || null;

        if (action === 'hide-stage' && stage) {
            cards.add(billId + '|' + stage);
            if (isolated && isolated !== billId) isolated = null;
        } else if (action === 'hide-bill') {
            bills.add(billId);
            [...cards].forEach(k => {
                if (k.indexOf(billId + '|') === 0) cards.delete(k);
            });
            if (isolated === billId) isolated = null;
        } else if (action === 'isolate-bill') {
            isolated = (isolated === billId) ? null : billId;
            bills.delete(billId);
        } else if (action === 'show-bill') {
            bills.delete(billId);
            [...cards].forEach(k => {
                if (k.indexOf(billId + '|') === 0) cards.delete(k);
            });
            if (isolated === billId) isolated = null;
        }
        writeStore([...bills], [...cards], isolated);
        closeMenu();
    }

    // Dismiss on outside click, Escape, scroll, or window resize.
    function onDocClick(e) {
        const m = menuEl();
        if (m && m.contains(e.target)) return;
        closeMenu();
    }
    function onKey(e) {
        if (e.key === 'Escape') closeMenu();
    }

    function install() {
        if (window.__cardMenuBound) return;
        window.__cardMenuBound = true;
        document.addEventListener('contextmenu', onContextMenu);
        document.addEventListener('click', onLegendIconClick, true);
        const m = menuEl();
        if (m) m.addEventListener('click', onMenuClick);
        else {
            // Menu not in DOM yet — retry once the layout mounts.
            setTimeout(install.bind(null), 300);
            window.__cardMenuBound = false;
            return;
        }
        document.addEventListener('mousedown', onDocClick);
        document.addEventListener('keydown', onKey);
        window.addEventListener('scroll', closeMenu, true);
        window.addEventListener('resize', closeMenu);

        // Reset View button clears hide state. (timeline_zoom.js resets zoom
        // on its own click listener — both fire on the same button click.)
        document.addEventListener('click', (e) => {
            const btn = e.target.closest('#timeline-reset-btn');
            if (!btn) return;
            writeStore([], [], null);
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', install);
    } else {
        install();
    }
})();
