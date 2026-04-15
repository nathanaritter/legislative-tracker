"""
Deck-style title bar directly above the timeline. Mirrors the PPTX regulatory timeline:
left side has the context title + subtitle, right side has the status color legend.
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
                    html.Div("Filter bills on the left to scope the timeline.",
                              id="deck-subtitle", className="subtitle"),
                ]
            ),
            html.Div(legend_items, className="legend"),
        ],
        className="deck-title-bar",
    )
