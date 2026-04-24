"""
Navbar pills showing the data pipeline funnel per state: downloaded →
deterministic filter → AI-classified CRE-relevant → scored. Pipeline
counts come from _pipeline_stats.json written by the ETL run.py.
"""

import json
from pathlib import Path

from dash import Input, Output, callback, html

from loaders.bills import load_bills

_STATS_PATH = Path(__file__).resolve().parent.parent.parent / "etl-base" / "temp" / "legislation" / "_pipeline_stats.json"


def _load_stats():
    try:
        if _STATS_PATH.exists():
            return json.loads(_STATS_PATH.read_text())
    except Exception:
        pass
    return {}


@callback(
    Output("navbar-metadata", "children"),
    Input("filters-store", "data"),
)
def populate_navbar(filters):
    state = (filters or {}).get("states", [None])[0] if filters else None
    stats = _load_stats()
    st = stats.get(state, {}) if state else {}

    n_downloaded = st.get("downloaded", 0)
    n_filtered = st.get("deterministic_filter", 0)
    n_cre = st.get("cre_relevant", 0)
    n_scored = st.get("scored", 0)

    # If no stats file yet, fall back to live counts from bills.csv.
    if not st:
        bills = load_bills()
        if bills is not None and not bills.empty:
            scope = bills[bills["state"] == state] if state else bills
            n_downloaded = len(scope)
            n_filtered = n_downloaded
            n_cre = int(scope["cre_relevant"].fillna(False).astype(bool).sum()) if "cre_relevant" in scope.columns else 0
            n_scored = int(scope["ai_risk_score"].notna().sum()) if "ai_risk_score" in scope.columns else 0

    state_label = f" ({state})" if state else ""

    return [
        html.Span(
            [html.I(className="bi bi-download me-1"),
             f"{n_downloaded:,} downloaded{state_label}"],
            className="meta-pill",
        ),
        html.Span(
            [html.I(className="bi bi-funnel me-1"),
             f"{n_filtered:,} filtered"],
            className="meta-pill",
        ),
        html.Span(
            [html.I(className="bi bi-robot me-1"),
             f"{n_cre:,} CRE-relevant"],
            className="meta-pill",
        ),
        html.Span(
            [html.I(className="bi bi-bar-chart me-1"),
             f"{n_scored:,} scored"],
            className="meta-pill",
        ),
    ]
