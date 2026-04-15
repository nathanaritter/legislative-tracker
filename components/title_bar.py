"""
Compact deck-style title strip directly above the timeline. Kept small so the
timeline itself fits in the viewport without vertical scrolling.
"""

from dash import html

from config import LEGEND


def build_title_bar():
    legend_items = [
        html.Div(
            [
                html.Span(className="legend-dot", style={"background": color}),
                html.Span(label),
            ],
            className="legend-item",
        )
        for label, color in LEGEND
    ]

    return html.Div(
        [
            html.Div(
                [
                    html.Div("Regulatory Timeline", id="deck-title", className="title"),
                    html.Div(id="deck-subtitle", className="subtitle",
                              children="Filter bills on the left to scope the timeline."),
                ]
            ),
            html.Div(legend_items, className="legend"),
        ],
        className="deck-title-bar",
    )
