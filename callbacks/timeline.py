"""
Render the card-based timeline + right-side bill legend from current filters.

Hiding bills via the legend uses clientside JavaScript for instant toggling —
we don't round-trip through Python for simple show/hide. Python only re-renders
the timeline when the filter query itself changes (state, status, dates).
"""

from dash import Input, Output, State, callback, clientside_callback, ClientsideFunction, ctx, ALL, html, no_update

from components.timeline import render_timeline, canvas_style_for
from loaders.bills import filter_bills, get_events_for
from config import STATUS_GROUP


_STATUS_COLOR = {
    "introduced": "#6A4C93",
    "committee":  "#6A4C93",
    "passed":     "#1B5E83",
    "enacted":    "#2E7D32",
    "failed":     "#999999",
}


@callback(
    Output("timeline-canvas", "children"),
    Output("timeline-canvas", "style"),
    Output("timeline-meta", "children"),
    Output("bill-legend", "children"),
    Input("filters-store", "data"),
    Input("zoom-store", "data"),
)
def render(filters, zoom):
    filters = filters or {}
    zoom = float(zoom or 1.0)
    all_bills = filter_bills(filters)

    # Render ALL filtered bills — clientside JS will hide the ones flagged in
    # hidden-bills-store by toggling CSS `display: none`. This keeps the
    # expensive Python render off the click hot-path.
    events = get_events_for(all_bills["bill_id"].tolist()) if not all_bills.empty else None
    children, meta = render_timeline(all_bills, events, zoom=zoom)
    style = canvas_style_for(all_bills, events, zoom=zoom)

    legend_items = [html.H5("Bills in view")]
    if all_bills.empty:
        legend_items.append(html.Div("No bills.", style={"color": "#6b7280", "fontSize": "11px"}))
    else:
        sorted_bills = all_bills.sort_values(
            "last_action_date", ascending=False, na_position="last"
        )
        for _, row in sorted_bills.iterrows():
            bill_id = row["bill_id"]
            group = STATUS_GROUP.get(row.get("current_status") or "introduced", "introduced")
            color = _STATUS_COLOR.get(group, "#6A4C93")
            label = f"{row.get('bill_number','')} — {row.get('title','')}"
            legend_items.append(html.Div(
                [
                    html.Span(className="swatch", style={"background": color}),
                    html.Span(label, className="label", title=label),
                ],
                className="bill-legend-item",
                id={"type": "bill-legend-item", "bill_id": bill_id},
                n_clicks=0,
                **{"data-bill-id": bill_id},
            ))

    return children, style, meta, legend_items


# ----------------------------------------------------------------------------
# Clientside toggling: click a legend item -> update hidden-bills-store AND
# toggle the `.hidden` / `display: none` CSS on the matching legend item and
# every matching timeline card. No Python round-trip, so the UI responds in
# milliseconds no matter how many cards are rendered.
# ----------------------------------------------------------------------------

clientside_callback(
    """
    function(n_clicks_array, hidden) {
        const trig = window.dash_clientside.callback_context.triggered[0];
        if (!trig) return window.dash_clientside.no_update;
        // Parse which legend item fired
        let id;
        try { id = JSON.parse(trig.prop_id.split('.')[0]); }
        catch (e) { return window.dash_clientside.no_update; }
        if (!id || id.type !== 'bill-legend-item') return window.dash_clientside.no_update;
        if (!trig.value) return window.dash_clientside.no_update;  // fresh render, ignore

        const billId = id.bill_id;
        const set = new Set(hidden || []);
        if (set.has(billId)) set.delete(billId); else set.add(billId);
        const arr = [...set].sort();

        // Toggle the legend item's .hidden class
        document
            .querySelectorAll('.bill-legend-item')
            .forEach(el => {
                const did = el.getAttribute('data-bill-id');
                if (did) el.classList.toggle('hidden', set.has(did));
            });
        // Toggle display:none on every timeline card for this bill_id
        document
            .querySelectorAll('.bill-card')
            .forEach(el => {
                try {
                    const cid = JSON.parse(el.id || '{}');
                    if (cid && cid.bill_id) {
                        el.style.display = set.has(cid.bill_id) ? 'none' : '';
                    }
                } catch (e) {}
            });
        return arr;
    }
    """,
    Output("hidden-bills-store", "data"),
    Input({"type": "bill-legend-item", "bill_id": ALL}, "n_clicks"),
    State("hidden-bills-store", "data"),
    prevent_initial_call=True,
)


# After every timeline re-render we must re-apply the hidden state to the new
# DOM (legend items and cards), because clientside JS runs after each render.
clientside_callback(
    """
    function(_children, hidden) {
        const set = new Set(hidden || []);
        document.querySelectorAll('.bill-legend-item').forEach(el => {
            const did = el.getAttribute('data-bill-id');
            if (did) el.classList.toggle('hidden', set.has(did));
        });
        document.querySelectorAll('.bill-card').forEach(el => {
            try {
                const cid = JSON.parse(el.id || '{}');
                if (cid && cid.bill_id) {
                    el.style.display = set.has(cid.bill_id) ? 'none' : '';
                }
            } catch (e) {}
        });
        return window.dash_clientside.no_update;
    }
    """,
    Output("hidden-bills-store", "data", allow_duplicate=True),
    Input("timeline-canvas", "children"),
    State("hidden-bills-store", "data"),
    prevent_initial_call=True,
)


@callback(
    Output("zoom-store", "data"),
    Output("zoom-level-readout", "children"),
    Input("zoom-in-btn", "n_clicks"),
    Input("zoom-out-btn", "n_clicks"),
    Input("zoom-fit-btn", "n_clicks"),
    State("zoom-store", "data"),
    prevent_initial_call=True,
)
def change_zoom(_in, _out, _fit, current):
    trigger = ctx.triggered_id
    z = float(current or 1.0)
    if trigger == "zoom-in-btn":
        z = min(16.0, z * 1.5)
    elif trigger == "zoom-out-btn":
        z = max(0.2, z / 1.5)
    elif trigger == "zoom-fit-btn":
        z = 1.0
    return z, f"{int(round(z * 100))}%"


# Ctrl + mousewheel on the timeline = native-feeling zoom. The JS simply
# dispatches a click on the existing zoom-in/out button so the server-side
# callback is the single source of truth for the zoom factor. Runs after every
# re-render so the binding survives DOM updates.
clientside_callback(
    """
    function(_children) {
        const wrap = document.querySelector('.timeline-wrap');
        if (!wrap || wrap.__wheelBound) return window.dash_clientside.no_update;
        wrap.__wheelBound = true;
        let last = 0;
        wrap.addEventListener('wheel', (e) => {
            if (!(e.ctrlKey || e.metaKey)) return;   // preserve vertical scroll
            e.preventDefault();
            const now = Date.now();
            if (now - last < 40) return;
            last = now;
            const btnId = (e.deltaY < 0) ? 'zoom-in-btn' : 'zoom-out-btn';
            const btn = document.getElementById(btnId);
            if (btn) btn.click();
        }, {passive: false});
        return window.dash_clientside.no_update;
    }
    """,
    Output("zoom-store", "data", allow_duplicate=True),
    Input("timeline-canvas", "children"),
    prevent_initial_call=True,
)


# The Python toggle_hidden callback is replaced by the clientside_callback
# above — removed to avoid a duplicate Output registration that prevented the
# page from loading.
