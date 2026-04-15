"""
Topnav — matches the Milestone Investments nav style used in analytics-workbench
and contract-tracker. Gradient brand blue with the "The MILESTONE Group | App Name"
pattern on the left and contextual pills on the right.
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
            html.Div(
                [
                    html.Span(
                        [html.I(className="bi bi-bank2"), html.Span(id="nav-pill-bills", children="— bills")],
                        className="nav-pill",
                    ),
                    html.Span(
                        [html.I(className="bi bi-clock-history"), html.Span(id="nav-pill-update", children="No updates yet")],
                        className="nav-pill",
                    ),
                ],
                className="pills",
            ),
        ],
        className="app-topnav",
    )
