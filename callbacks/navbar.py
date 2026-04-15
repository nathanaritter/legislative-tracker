"""
Three navbar pills per user spec: bills scanned, CRE-relevant bills kept,
last data update timestamp. No adverse/status pill.
"""

from dash import Input, Output, callback, html

from loaders.bills import load_bills


@callback(
    Output("navbar-metadata", "children"),
    Input("filters-store", "data"),
)
def populate_navbar(_filters):
    # The pills reflect raw data ingest, not the current user filter — the user
    # wants to see pipeline health regardless of what they're currently viewing.
    bills = load_bills()
    n_scanned = len(bills) if bills is not None else 0

    if bills is None or bills.empty or "cre_relevant" not in bills.columns:
        n_kept = 0
    else:
        n_kept = int(bills["cre_relevant"].fillna(False).astype(bool).sum())

    last_str = "—"
    if bills is not None and not bills.empty and "last_action_date" in bills.columns:
        try:
            last = bills["last_action_date"].max()
            last_str = last.strftime("%Y-%m-%d %H:%M") if hasattr(last, "strftime") else str(last)[:16]
        except Exception:
            pass

    return [
        html.Span(
            [html.I(className="bi bi-database me-1"), f"{n_scanned} bills scanned"],
            className="meta-pill",
        ),
        html.Span(
            [html.I(className="bi bi-funnel me-1"), f"{n_kept} CRE-relevant"],
            className="meta-pill",
        ),
        html.Span(
            [html.I(className="bi bi-clock me-1"), f"Last update: {last_str}"],
            className="meta-pill",
        ),
    ]
