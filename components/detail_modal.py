"""
Detail modal for a single bill. Shows:
  - Total risk score in a brand-blue medallion
  - Each score component rendered as a same-length normalized bar so magnitudes
    are visually comparable regardless of their raw weight
  - A one-line definition of each component and (when available) an AI
    rationale explaining the score
  - AI summary, sponsors grid, subject pills, download button

All bars use dark brand blue so the user isn't distracted by arbitrary palette
choices.
"""

import json

import pandas as pd
from dash import html, dcc
import dash_bootstrap_components as dbc
import dash_ag_grid as dag

from config import BRAND_COLOR, GRAY_500


RISK_COMPONENTS = [
    ("operational_impact", 30, "Operational impact",
     "How the bill changes day-to-day property operations — rent setting, leasing, evictions, inspections."),
    ("capital_cost_impact", 25, "Capital cost impact",
     "Mandated capex, new taxes, or fees the bill would impose on owners and operators."),
    ("passage_probability", 20, "Passage probability",
     "Likelihood the bill becomes law based on current status, sponsor count, and majority-party alignment."),
    ("scope_breadth", 15, "Scope breadth",
     "How much of the market the bill touches — jurisdiction population times asset classes affected."),
    ("urgency", 10, "Urgency",
     "Proximity of effective date or scheduled vote — higher means sooner action is needed."),
]


DIRECTION_LABELS = {
    "favorable": ("Favorable for CRE", "▲", "dir-favorable"),
    "adverse":   ("Adverse for CRE",  "▼", "dir-adverse"),
    "mixed":     ("Mixed impact",     "◆", "dir-mixed"),
    "neutral":   ("Neutral",          "●", "dir-neutral"),
}


def build_risk_summary(score, direction=None):
    try:
        s = float(score) if score is not None and not pd.isna(score) else None
    except Exception:
        s = None
    value = f"{int(round(s))}" if s is not None else "—"
    d = (direction or "").lower()
    label, glyph, cls = DIRECTION_LABELS.get(d, (None, None, None))
    dir_badge = (
        html.Div([html.Span(glyph, className=f"direction-glyph {cls}"),
                  html.Span(label, className="direction-label")],
                 className="direction-badge")
        if label else None
    )
    return html.Div(
        [
            html.Div([html.Span(value, className="value"), html.Span("/ 100", className="suffix")],
                     className="risk-summary-score"),
            html.Div(
                [
                    html.Div("Composite impact score",
                              style={"fontSize": "12px", "textTransform": "uppercase",
                                      "letterSpacing": "0.05em", "color": GRAY_500, "fontWeight": "600"}),
                    html.Div("Weighted magnitude across the five components below (scale 0–100).",
                              style={"fontSize": "11px", "color": GRAY_500, "marginTop": "2px"}),
                ],
                style={"flex": "1"},
            ),
            dir_badge,
        ],
        className="risk-summary-row",
    )


def build_breakdown(breakdown_json, rationale_json=None):
    try:
        data = json.loads(breakdown_json) if isinstance(breakdown_json, str) else (breakdown_json or {})
    except Exception:
        data = {}
    try:
        rationales = (json.loads(rationale_json) if isinstance(rationale_json, str)
                       else (rationale_json or {}))
    except Exception:
        rationales = {}

    rows = []
    for key, max_pts, label, desc in RISK_COMPONENTS:
        value = 0.0
        try:
            value = float(data.get(key, 0) or 0)
        except Exception:
            value = 0.0
        pct = max(0.0, min(1.0, value / max_pts if max_pts else 0.0))
        rationale = rationales.get(key) if isinstance(rationales, dict) else None

        rows.append(html.Div(
            [
                html.Div(label, className="name"),
                html.Div(
                    html.Div(className="bar-fill",
                             style={"width": f"{pct * 100:.1f}%"}),
                    className="bar-track",
                ),
                html.Div(f"{value:.0f} / {max_pts}", className="score"),
                html.Div(desc, className="desc"),
                (html.Div(rationale, className="risk-rationale") if rationale else None),
            ],
            className="risk-row",
        ))

    return html.Div(rows, className="risk-breakdown")


# Legacy figure hooks are kept as no-op stubs so the old detail.py callback still wires up.
def build_risk_gauge(score):
    import plotly.graph_objects as go
    return go.Figure()


def build_breakdown_chart(breakdown_json):
    import plotly.graph_objects as go
    return go.Figure()


SPONSOR_COLUMNS = [
    {"field": "name", "headerName": "Name", "width": 180},
    {"field": "party", "headerName": "Party", "width": 70},
    {"field": "role", "headerName": "Role", "width": 130},
    {"field": "district", "headerName": "District", "width": 90},
]


def build_detail_modal():
    return dbc.Modal(
        [
            dbc.ModalHeader(dbc.ModalTitle(id="detail-title", className="modal-title")),
            dbc.ModalBody(
                [
                    html.Div(id="detail-meta",
                              style={"color": GRAY_500, "marginBottom": "12px", "fontSize": "12px"}),

                    html.Div(id="detail-risk-summary"),
                    html.Div(id="detail-risk-breakdown"),

                    html.Div("AI summary", className="modal-section-heading"),
                    dcc.Markdown(id="detail-summary", style={"fontSize": "12px", "lineHeight": "1.5"}),

                    html.Div("Sponsors", className="modal-section-heading"),
                    dag.AgGrid(
                        id="detail-sponsors-grid",
                        columnDefs=SPONSOR_COLUMNS,
                        rowData=[],
                        defaultColDef={"sortable": True, "resizable": True},
                        className="ag-theme-alpine",
                        style={"height": "160px", "width": "100%"},
                    ),

                    html.Div("Subjects", className="modal-section-heading"),
                    html.Div(id="detail-subjects"),
                ]
            ),
            dbc.ModalFooter(
                [
                    dbc.Button(
                        [html.I(className="bi bi-file-earmark-pdf", style={"marginRight": "6px"}), "Download full text"],
                        id="detail-download-btn",
                        color="primary",
                        href="#",
                        external_link=True,
                        target="_blank",
                        disabled=True,
                    ),
                    dbc.Button("Close", id="detail-close-btn", color="secondary", outline=True, className="ms-2"),
                ]
            ),
        ],
        id="detail-modal",
        size="lg",
        is_open=False,
        scrollable=True,
    )
