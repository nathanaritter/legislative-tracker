"""
Top-level layout: topnav + filters sidebar + main area + right-side bill legend.
"""

from dash import html, dcc

from components.navbar import build_navbar
from components.title_bar import build_title_bar
from components.sidebar import build_sidebar
from components.timeline import build_timeline_card_area
from components.detail_modal import build_detail_modal


def build_layout():
    return html.Div(
        [
            dcc.Store(id="filters-store", storage_type="session", data={}),
            dcc.Store(id="selected-bill-store", storage_type="memory", data=None),
            dcc.Store(id="hidden-bills-store", storage_type="session", data=[]),

            build_navbar(),
            html.Div(
                [
                    build_sidebar(),
                    html.Div(
                        [
                            build_title_bar(),
                            build_timeline_card_area(),
                        ],
                        className="app-main",
                    ),
                    html.Div(id="bill-legend", className="bill-legend"),
                ],
                className="app-shell",
            ),
            build_detail_modal(),
        ]
    )
