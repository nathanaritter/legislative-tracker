"""
Compact deck-style title strip directly above the timeline. Kept small so the
timeline itself fits in the viewport without vertical scrolling.
"""

from dash import html

from config import LEGEND, DIRECTION_LEGEND


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
    # Direction glyphs — so the ▲ ▼ ◆ shown on cards and in the right sidebar
    # are explained in the title-bar legend.
    for label, glyph, color in DIRECTION_LEGEND:
        legend_items.append(html.Div(
            [
                html.Span(glyph, className="legend-glyph",
                          style={"color": color, "fontWeight": "700"}),
                html.Span(label),
            ],
            className="legend-item",
        ))

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
