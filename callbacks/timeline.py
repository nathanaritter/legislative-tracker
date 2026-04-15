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

_DIRECTION_GLYPH = {
    "favorable": ("▲", "#059669"),
    "adverse":   ("▼", "#dc2626"),
    "mixed":     ("◆", "#d97706"),
    "neutral":   ("●", "#6b7280"),
}


@callback(
    Output("timeline-canvas", "children"),
    Output("timeline-canvas", "style"),
    Output("timeline-meta", "children"),
    Output("bill-legend", "children"),
    Input("filters-store", "data"),
)
def render(filters):
    filters = filters or {}
    all_bills = filter_bills(filters)

    # Render ALL filtered bills — clientside JS will hide the ones flagged in
    # hidden-bills-store by toggling CSS `display: none`. This keeps the
    # expensive Python render off the click hot-path.
    events = get_events_for(all_bills["bill_id"].tolist()) if not all_bills.empty else None
    children, meta = render_timeline(all_bills, events)
    style = canvas_style_for(all_bills, events)

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
            direction = (row.get("impact_direction") or "").lower()
            dir_glyph, dir_color = _DIRECTION_GLYPH.get(direction, ("", None))
            glyph_el = (
                html.Span(dir_glyph, className="legend-dir",
                          style={"color": dir_color, "marginRight": "2px"},
                          title={"favorable": "Favorable for CRE",
                                 "adverse": "Adverse for CRE",
                                 "mixed": "Mixed impact",
                                 "neutral": "Neutral"}.get(direction, ""))
                if dir_glyph else None
            )
            label_children = [glyph_el, label] if glyph_el is not None else [label]
            legend_items.append(html.Div(
                [
                    html.Span(
                        className="swatch",
                        style={"background": color},
                        id={"type": "bill-legend-swatch", "bill_id": bill_id},
                        n_clicks=0,
                        title="Click to hide / show",
                    ),
                    html.Span(
                        label_children,
                        className="label",
                        title=label,
                        id={"type": "bill-legend-label", "bill_id": bill_id},
                        n_clicks=0,
                    ),
                ],
                className="bill-legend-item",
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
        let id;
        try { id = JSON.parse(trig.prop_id.split('.')[0]); }
        catch (e) { return window.dash_clientside.no_update; }
        if (!id || id.type !== 'bill-legend-swatch') return window.dash_clientside.no_update;
        if (!trig.value) return window.dash_clientside.no_update;  // fresh render, ignore

        const billId = id.bill_id;
        const set = new Set(hidden || []);
        if (set.has(billId)) set.delete(billId); else set.add(billId);
        const arr = [...set].sort();

        document
            .querySelectorAll('.bill-legend-item')
            .forEach(el => {
                const did = el.getAttribute('data-bill-id');
                if (did) el.classList.toggle('hidden', set.has(did));
            });
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
        document
            .querySelectorAll('.timeline-dot[data-bill-id], .timeline-connector[data-bill-id]')
            .forEach(el => {
                const did = el.getAttribute('data-bill-id');
                if (did) el.style.display = set.has(did) ? 'none' : '';
            });
        // Re-pack row assignments so visible cards collapse into empty rows.
        if (typeof window.repackTimeline === 'function') window.repackTimeline();
        return arr;
    }
    """,
    Output("hidden-bills-store", "data"),
    Input({"type": "bill-legend-swatch", "bill_id": ALL}, "n_clicks"),
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
        document
            .querySelectorAll('.timeline-dot[data-bill-id], .timeline-connector[data-bill-id]')
            .forEach(el => {
                const did = el.getAttribute('data-bill-id');
                if (did) el.style.display = set.has(did) ? 'none' : '';
            });
        if (typeof window.repackTimeline === 'function') window.repackTimeline();
        return window.dash_clientside.no_update;
    }
    """,
    Output("hidden-bills-store", "data", allow_duplicate=True),
    Input("timeline-canvas", "children"),
    State("hidden-bills-store", "data"),
    prevent_initial_call=True,
)


# Zoom is handled entirely by assets/timeline_zoom.js — pure clientside drag/
# wheel/dblclick, no server callback.


# The Python toggle_hidden callback is replaced by the clientside_callback
# above — removed to avoid a duplicate Output registration that prevented the
# page from loading.
