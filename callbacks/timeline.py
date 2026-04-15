"""
Render the timeline figure + bill grid from current filters.
"""

from dash import Input, Output, callback

from components.timeline import build_timeline, empty_figure
from loaders.bills import filter_bills, get_events_for
from config import GRAY_500


@callback(
    Output("timeline-figure", "figure"),
    Output("timeline-meta", "children"),
    Output("bill-grid", "rowData"),
    Input("filters-store", "data"),
)
def render_timeline(filters):
    filters = filters or {}
    bills = filter_bills(filters)

    if bills.empty:
        return empty_figure(), "0 bills match current filters", []

    events = get_events_for(bills["bill_id"].tolist())
    fig = build_timeline(bills, events)

    total = len(bills)
    shown = min(total, 80)
    meta = f"Showing {shown} of {total} bills"
    if total > 80:
        meta += " — narrow filters to see more"

    grid_cols = ["bill_id", "state", "bill_number", "title", "current_status",
                 "ai_risk_score", "introduced_date", "last_action_date", "jurisdiction_name"]
    grid_rows = bills[[c for c in grid_cols if c in bills.columns]].copy()
    for dc in ("introduced_date", "last_action_date"):
        if dc in grid_rows.columns:
            grid_rows[dc] = grid_rows[dc].dt.strftime("%Y-%m-%d").fillna("")

    return fig, meta, grid_rows.to_dict("records")
