"""
Sidebar filter stack. State is single-select (only one state at a time),
counties and cities are multi-select, 5 consolidated status buckets, risk
slider with live value readout, and a preset bar for the date range.
"""

from datetime import date, timedelta

from dash import html, dcc
import dash_bootstrap_components as dbc

from config import STATES, STATUS_GROUPS, CRE_SUBJECTS


def _opts(values):
    return [{"label": label, "value": code} for code, label in values]


def _subject_opts():
    return [{"label": s.replace("_", " ").title(), "value": s} for s in CRE_SUBJECTS]


def build_sidebar():
    today = date.today()
    default_start = today - timedelta(days=365 * 3)

    return html.Div(
        [
            html.H6("State"),
            dcc.Dropdown(
                id="state-filter",
                options=[{"label": s, "value": s} for s in STATES],
                value=None, multi=False,
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
                options=_opts(STATUS_GROUPS),
                value=[], multi=True,
                placeholder="Any status",
                className="dash-dropdown filter-row",
            ),

            html.H6("Subject"),
            dcc.Dropdown(
                id="subject-filter",
                options=_subject_opts(),
                value=[], multi=True,
                placeholder="Any subject",
                className="dash-dropdown filter-row",
            ),

            html.H6("Risk score"),
            dcc.RangeSlider(
                id="risk-filter",
                min=0, max=100, step=1,
                value=[0, 100],
                marks=None,
                tooltip={"placement": "bottom", "always_visible": False},
                className="filter-row brand-slider",
            ),

            html.H6("Date range"),
            html.Div(
                [
                    html.Div(
                        [
                            html.Div("Start", className="date-label"),
                            dcc.Input(
                                id="date-filter-start",
                                type="date",
                                value=default_start.isoformat(),
                                className="brand-dateinput",
                            ),
                        ]
                    ),
                    html.Div(
                        [
                            html.Div("End", className="date-label"),
                            dcc.Input(
                                id="date-filter-end",
                                type="date",
                                value=today.isoformat(),
                                className="brand-dateinput",
                            ),
                        ]
                    ),
                ],
                className="date-range-row",
            ),

            html.Hr(style={"margin": "14px 0 10px"}),
            dbc.Button(
                [html.I(className="bi bi-arrow-repeat", style={"marginRight": "6px"}), "Reset filters"],
                id="reset-filters-btn",
                color="secondary", outline=True, size="sm",
                style={"width": "100%"},
            ),
        ],
        className="app-sidebar",
    )
