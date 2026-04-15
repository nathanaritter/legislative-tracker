"""
Populate the navbar pills. Four pills mirror analytics-workbench's exactly:
  - total bill count
  - total stage-event count
  - last update timestamp
  - adverse-bill count (status indicator — red pill when non-zero)
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

    # Stage-event count across currently-visible bills
    events = get_events_for(bills["bill_id"].tolist()) if not bills.empty else None
    n_events = len(events) if events is not None else 0

    if not bills.empty and "last_action_date" in bills.columns:
        try:
            last = bills["last_action_date"].max()
            last_str = last.strftime("%Y-%m-%d") if hasattr(last, "strftime") else str(last)[:10]
        except Exception:
            last_str = "—"
    else:
        last_str = "—"

    # Adverse bill count — surface red pill when any adverse bills are active
    adverse = 0
    if not bills.empty and "impact_direction" in bills.columns:
        adverse = int((bills["impact_direction"] == "adverse").sum())

    status_class = "meta-pill meta-pill--error" if adverse else "meta-pill"
    status_label = f"{adverse} adverse" if adverse else "No adverse bills"

    return [
        html.Span(
            [html.I(className="bi bi-journal-text me-1"), f"{n_bills} bills"],
            className="meta-pill",
        ),
        html.Span(
            [html.I(className="bi bi-diagram-3 me-1"), f"{n_events} stage events"],
            className="meta-pill",
        ),
        html.Span(
            [html.I(className="bi bi-clock me-1"), f"Last update: {last_str}"],
            className="meta-pill",
        ),
        html.Span(
            [html.I(className="bi bi-exclamation-triangle me-1"), status_label],
            className=status_class,
        ),
    ]
