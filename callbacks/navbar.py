"""
Four navbar pills matching analytics-workbench exactly (same icons, same
label format): bill count, stage-event count, last-update timestamp with
HH:MM, and an adverse-bills status pill that flips red when > 0.
"""

from datetime import datetime

from dash import Input, Output, callback, html

from loaders.bills import filter_bills, get_events_for


@callback(
    Output("navbar-metadata", "children"),
    Input("filters-store", "data"),
)
def populate_navbar(filters):
    bills = filter_bills(filters or {})
    n_bills = len(bills)

    events = get_events_for(bills["bill_id"].tolist()) if not bills.empty else None
    n_events = len(events) if events is not None else 0

    if not bills.empty and "last_action_date" in bills.columns:
        try:
            last = bills["last_action_date"].max()
            last_str = (last.strftime("%Y-%m-%d %H:%M")
                        if hasattr(last, "strftime") else str(last)[:16])
        except Exception:
            last_str = "—"
    else:
        last_str = "—"

    adverse = 0
    favorable = 0
    if not bills.empty and "impact_direction" in bills.columns:
        adverse = int((bills["impact_direction"] == "adverse").sum())
        favorable = int((bills["impact_direction"] == "favorable").sum())

    status_class = "meta-pill meta-pill--error" if adverse else "meta-pill"
    status_label = f"{adverse}/{n_bills} adverse" if n_bills else "0 bills"

    return [
        html.Span(
            [html.I(className="bi bi-database me-1"), f"{n_bills} bills"],
            className="meta-pill",
        ),
        html.Span(
            [html.I(className="bi bi-graph-up me-1"), f"{n_events} stage events"],
            className="meta-pill",
        ),
        html.Span(
            [html.I(className="bi bi-clock me-1"), f"Last update: {last_str}"],
            className="meta-pill",
        ),
        html.Span(
            [html.I(className="bi bi-check2-circle me-1"), status_label],
            className=status_class,
        ),
    ]
