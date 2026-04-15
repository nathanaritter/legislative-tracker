"""
Detail modal shown when a timeline segment or grid row is clicked.
Displays AI summary, risk score gauge + breakdown, sponsors, and a text download button.
"""

import json

import pandas as pd
import plotly.graph_objects as go
from dash import html, dcc
import dash_bootstrap_components as dbc
import dash_ag_grid as dag

from config import BRAND_COLOR, ACCENT_COLOR, POSITIVE_COLOR, WARNING_COLOR, NEGATIVE_COLOR, GRAY_500


def risk_class(score):
    if score is None or pd.isna(score):
        return ("—", "risk-low")
    if score < 40:
        return (f"{score:.0f}", "risk-low")
    if score < 70:
        return (f"{score:.0f}", "risk-mid")
    return (f"{score:.0f}", "risk-high")


def build_risk_gauge(score):
    value = 0 if score is None or pd.isna(score) else float(score)
    color = POSITIVE_COLOR if value < 40 else (WARNING_COLOR if value < 70 else NEGATIVE_COLOR)
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=value,
        number={"font": {"size": 28, "color": BRAND_COLOR}},
        gauge={
            "axis": {"range": [0, 100], "tickwidth": 1},
            "bar": {"color": color},
            "steps": [
                {"range": [0, 40], "color": "#d1fae5"},
                {"range": [40, 70], "color": "#fef3c7"},
                {"range": [70, 100], "color": "#fee2e2"},
            ],
        },
        domain={"x": [0, 1], "y": [0, 1]},
    ))
    fig.update_layout(margin=dict(l=10, r=10, t=10, b=10), height=180)
    return fig


def build_breakdown_chart(breakdown_json):
    try:
        data = json.loads(breakdown_json) if isinstance(breakdown_json, str) else (breakdown_json or {})
    except Exception:
        data = {}

    components = [
        ("operational_impact", 30),
        ("capital_cost_impact", 25),
        ("passage_probability", 20),
        ("scope_breadth", 15),
        ("urgency", 10),
    ]
    labels = [c[0].replace("_", " ").title() for c in components]
    maxes = [c[1] for c in components]
    values = [float(data.get(c[0], 0) or 0) for c in components]

    fig = go.Figure()
    fig.add_trace(go.Bar(y=labels, x=maxes, orientation="h",
                        marker=dict(color="#e5e7eb", line=dict(width=0)),
                        showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Bar(y=labels, x=values, orientation="h",
                        marker=dict(color=ACCENT_COLOR, line=dict(width=0)),
                        text=[f"{v:.0f}/{m}" for v, m in zip(values, maxes)],
                        textposition="inside", showlegend=False,
                        hovertemplate="%{y}: %{x:.1f}<extra></extra>"))
    fig.update_layout(
        barmode="overlay",
        xaxis=dict(range=[0, 30], showgrid=False),
        yaxis=dict(tickfont=dict(size=11)),
        margin=dict(l=10, r=10, t=10, b=10),
        height=200, plot_bgcolor="#fff",
    )
    return fig


def build_detail_modal():
    return dbc.Modal(
        [
            dbc.ModalHeader(dbc.ModalTitle(id="detail-title", className="modal-title")),
            dbc.ModalBody(
                [
                    html.Div(id="detail-meta", style={"color": GRAY_500, "marginBottom": "12px"}),

                    html.Div(
                        [
                            html.Div(
                                [html.H6("Risk score"), dcc.Graph(id="detail-risk-gauge", config={"displayModeBar": False})],
                                style={"flex": "1"},
                            ),
                            html.Div(
                                [html.H6("Risk breakdown"), dcc.Graph(id="detail-risk-breakdown", config={"displayModeBar": False})],
                                style={"flex": "2", "marginLeft": "16px"},
                            ),
                        ],
                        style={"display": "flex"},
                    ),

                    html.H6("AI summary", style={"marginTop": "16px"}),
                    dcc.Markdown(id="detail-summary", style={"fontSize": "13px"}),

                    html.H6("Sponsors", style={"marginTop": "16px"}),
                    dag.AgGrid(
                        id="detail-sponsors-grid",
                        columnDefs=[
                            {"field": "name", "flex": 2},
                            {"field": "party", "width": 80},
                            {"field": "role", "width": 110},
                            {"field": "district", "width": 110},
                        ],
                        rowData=[],
                        defaultColDef={"sortable": True, "resizable": True},
                        className="ag-theme-alpine",
                        style={"height": "180px"},
                    ),

                    html.H6("Subjects", style={"marginTop": "16px"}),
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
        size="xl",
        is_open=False,
        scrollable=True,
    )
