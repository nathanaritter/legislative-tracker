"""
Sidebar filter stack: state → counties → cities, plus status / subject / risk / date.
"""

from datetime import date, timedelta

from dash import html, dcc
import dash_bootstrap_components as dbc

from config import STATES, BILL_STATUSES, CRE_SUBJECTS


def _opts(values):
    return [{"label": v.replace("_", " ").title(), "value": v} for v in values]


def build_sidebar():
    today = date.today()
    default_start = today - timedelta(days=365 * 3)

    return html.Div(
        [
            html.H6("States"),
            dcc.Dropdown(
                id="state-filter",
                options=[{"label": s, "value": s} for s in STATES],
                value=[],
                multi=True,
                placeholder="All states",
                className="dash-dropdown filter-row",
            ),

            html.H6("Counties"),
            dcc.Dropdown(
                id="county-filter",
                options=[], value=[], multi=True,
                placeholder="All counties",
                className="dash-dropdown filter-row",
            ),

            html.H6("Cities"),
            dcc.Dropdown(
                id="city-filter",
                options=[], value=[], multi=True,
                placeholder="All cities",
                className="dash-dropdown filter-row",
            ),

            html.H6("Status"),
            dcc.Dropdown(
                id="status-filter",
                options=_opts(BILL_STATUSES),
                value=[], multi=True,
                placeholder="Any status",
                className="dash-dropdown filter-row",
            ),

            html.H6("Subject"),
            dcc.Dropdown(
                id="subject-filter",
                options=_opts(CRE_SUBJECTS),
                value=[], multi=True,
                placeholder="Any CRE subject",
                className="dash-dropdown filter-row",
            ),

            html.H6("Risk score"),
            dcc.RangeSlider(
                id="risk-filter",
                min=0, max=100, step=5,
                value=[0, 100],
                marks={0: "0", 50: "50", 100: "100"},
                tooltip={"placement": "bottom", "always_visible": False},
                className="filter-row",
            ),

            html.H6("Date range"),
            dcc.DatePickerRange(
                id="date-filter",
                start_date=default_start,
                end_date=today,
                display_format="YYYY-MM-DD",
                className="filter-row",
                style={"width": "100%"},
            ),

            dbc.Checklist(
                id="cre-only-filter",
                options=[{"label": " CRE-relevant only", "value": "on"}],
                value=["on"],
                className="filter-row",
                style={"marginTop": "12px", "fontSize": "12px"},
            ),

            html.Hr(style={"margin": "12px 0"}),
            dbc.Button(
                [html.I(className="bi bi-arrow-repeat", style={"marginRight": "6px"}), "Reset filters"],
                id="reset-filters-btn",
                color="secondary",
                outline=True,
                size="sm",
                style={"width": "100%"},
            ),
        ],
        className="app-sidebar",
    )
