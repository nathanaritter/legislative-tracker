"""
Top-level layout: topnav + sidebar + main area + detail modal.
"""

from dash import html, dcc
import dash_bootstrap_components as dbc

from components.sidebar import build_sidebar
from components.timeline import build_timeline_card
from components.bill_grid import build_bill_grid_card
from components.detail_modal import build_detail_modal


def build_layout():
    return html.Div(
        [
            # Stores — filter state + currently selected bill
            dcc.Store(id="filters-store", storage_type="session", data={}),
            dcc.Store(id="selected-bill-store", storage_type="memory", data=None),

            html.Div(
                [
                    html.I(className="bi bi-bank2", style={"marginRight": "10px", "fontSize": "18px"}),
                    html.Span("Legislative Tracker", className="title"),
                ],
                className="app-topnav",
            ),
            html.Div(
                [
                    build_sidebar(),
                    html.Div(
                        [
                            build_timeline_card(),
                            build_bill_grid_card(),
                        ],
                        className="app-main",
                    ),
                ],
                className="app-shell",
            ),
            build_detail_modal(),
        ]
    )
