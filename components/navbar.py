"""
Topnav — identical chrome to analytics-workbench / contract-tracker: gradient
brand blue, tmg-logo, "The MILESTONE Group" wordmark, divider, app title,
then `meta-pill` stats on the right populated by a callback.
"""

from dash import html


def build_navbar():
    return html.Div(
        [
            html.Div(
                [
                    html.Img(src="/assets/tmg-logo.png"),
                    html.Span("|", className="divider"),
                    html.Span("Legislative Tracker v0.1", className="title"),
                ],
                className="brand",
            ),
            html.Div(id="navbar-metadata",
                     style={"display": "flex", "alignItems": "center", "gap": "8px"}),
        ],
        className="app-topnav",
    )
