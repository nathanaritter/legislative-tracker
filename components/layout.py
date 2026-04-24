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
            # Memory storage — hidden-bills and any transient view state should
            # clear on hard refresh so the user doesn't get stuck with stale
            # state they can't see.
            dcc.Store(id="hidden-bills-store", storage_type="memory",
                      data={"bills": [], "cards": [], "isolated": None}),
            # Throwaway sink for clientside read-through callbacks (shadowing
            # hidden-bills-store into a window global for the right-click menu JS).
            dcc.Store(id="_shadow-sink", storage_type="memory", data=None),

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
            # Bill actions menu. Opened by right-clicking a card on the
            # timeline OR by left-clicking the eye icon in the right legend.
            # card_menu.js handles positioning, show/hide, and action dispatch.
            html.Div(
                [
                    html.Div("Bill actions", className="cm-heading"),
                    html.Div("Isolate this bill", className="cm-item",
                             **{"data-action": "isolate-bill"}),
                    html.Div("Hide this stage", className="cm-item",
                             **{"data-action": "hide-stage"}),
                    html.Div("Hide whole bill", className="cm-item",
                             **{"data-action": "hide-bill"}),
                    html.Div("Show this bill", className="cm-item",
                             **{"data-action": "show-bill"}),
                ],
                id="card-context-menu",
                className="card-context-menu",
            ),
        ]
    )
