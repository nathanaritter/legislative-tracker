"""
Render the card-based timeline + right-side bill legend from current filters.
The legend lets users hide/show individual bills; hidden-bill IDs live in
`hidden-bills-store`.
"""

from dash import Input, Output, State, callback, ctx, ALL, html, no_update

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
    Input("hidden-bills-store", "data"),
    Input("zoom-store", "data"),
)
def render(filters, hidden_list, zoom):
    filters = filters or {}
    zoom = float(zoom or 1.0)
    all_bills = filter_bills(filters)
    hidden = set(hidden_list or [])

    visible = all_bills[~all_bills["bill_id"].isin(hidden)] if not all_bills.empty else all_bills

    events = get_events_for(visible["bill_id"].tolist()) if not visible.empty else None
    children, meta = render_timeline(visible, events, zoom=zoom)
    style = canvas_style_for(visible, events, zoom=zoom)

    legend_items = [html.H5("Bills in view")]
    if all_bills.empty:
        legend_items.append(html.Div("No bills.", style={"color": "#6b7280", "fontSize": "11px"}))
    else:
        sorted_bills = all_bills.sort_values(
            "last_action_date", ascending=False, na_position="last"
        )
        for _, row in sorted_bills.iterrows():
            bill_id = row["bill_id"]
            is_hidden = bill_id in hidden
            group = STATUS_GROUP.get(row.get("current_status") or "introduced", "introduced")
            color = _STATUS_COLOR.get(group, "#6A4C93")
            label = f"{row.get('bill_number','')} — {row.get('title','')}"
            legend_items.append(html.Div(
                [
                    html.Span(className="swatch", style={"background": color}),
                    html.Span(label, className="label", title=label),
                ],
                className=f"bill-legend-item{' hidden' if is_hidden else ''}",
                id={"type": "bill-legend-item", "bill_id": bill_id},
                n_clicks=0,
            ))

    return children, style, meta, legend_items


@callback(
    Output("zoom-store", "data"),
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
        z = min(4.0, z * 1.35)
    elif trigger == "zoom-out-btn":
        z = max(0.25, z / 1.35)
    elif trigger == "zoom-fit-btn":
        z = 1.0
    return z


@callback(
    Output("hidden-bills-store", "data"),
    Input({"type": "bill-legend-item", "bill_id": ALL}, "n_clicks"),
    State("hidden-bills-store", "data"),
    prevent_initial_call=True,
)
def toggle_hidden(_clicks, hidden_list):
    trigger = ctx.triggered_id
    if not isinstance(trigger, dict) or trigger.get("type") != "bill-legend-item":
        return no_update
    bill_id = trigger["bill_id"]
    hidden = set(hidden_list or [])
    if bill_id in hidden:
        hidden.remove(bill_id)
    else:
        hidden.add(bill_id)
    return sorted(hidden)
