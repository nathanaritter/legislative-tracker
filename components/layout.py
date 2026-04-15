"""
Top-level layout: Milestone topnav + PPTX-style title bar + sidebar + main area + detail modal.
"""

from dash import html, dcc

from components.navbar import build_navbar
from components.title_bar import build_title_bar
from components.sidebar import build_sidebar
from components.timeline import build_timeline_card_area
from components.bill_grid import build_bill_grid_card
from components.detail_modal import build_detail_modal


def build_layout():
    return html.Div(
        [
            dcc.Store(id="filters-store", storage_type="session", data={}),
            dcc.Store(id="selected-bill-store", storage_type="memory", data=None),

            build_navbar(),
            html.Div(
                [
                    build_sidebar(),
                    html.Div(
                        [
                            build_title_bar(),
                            build_timeline_card_area(),
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
