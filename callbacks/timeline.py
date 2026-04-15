"""
Render the card-based timeline and populate the bill grid from current filters.
"""

from dash import Input, Output, callback

from components.timeline import render_timeline, canvas_style_for
from loaders.bills import filter_bills


@callback(
    Output("timeline-canvas", "children"),
    Output("timeline-canvas", "style"),
    Output("timeline-meta", "children"),
    Output("bill-grid", "rowData"),
    Output("nav-pill-bills", "children"),
    Input("filters-store", "data"),
)
def render(filters):
    filters = filters or {}
    bills = filter_bills(filters)

    children, meta = render_timeline(bills)
    style = canvas_style_for(bills)

    grid_cols = ["bill_id", "state", "bill_number", "title", "current_status",
                 "ai_risk_score", "introduced_date", "last_action_date", "jurisdiction_name"]
    if bills.empty:
        grid_rows = []
    else:
        grid_rows = bills[[c for c in grid_cols if c in bills.columns]].copy()
        for dc in ("introduced_date", "last_action_date"):
            if dc in grid_rows.columns:
                grid_rows[dc] = grid_rows[dc].dt.strftime("%Y-%m-%d").fillna("")
        grid_rows = grid_rows.to_dict("records")

    pill_bills = f"{len(bills)} bills"
    return children, style, meta, grid_rows, pill_bills
