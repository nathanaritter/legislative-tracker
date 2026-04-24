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
     "How much the bill changes how you run apartments day-to-day."),
    ("capital_cost_impact", 20, "Capital cost impact",
     "How much one-time spending the bill forces on apartment buildings."),
    ("pnl_impact", 25, "P&L impact",
     "How much the bill changes ongoing cashflow at the property."),
    ("scope_breadth", 15, "Scope breadth",
     "How much of the multifamily asset class the bill reaches."),
    ("enforcement_teeth", 10, "Enforcement teeth",
     "How aggressively the bill can be enforced against owners."),
]


# Backwards-compat read alias: earlier Stage-2 runs used a single combined
# `capital_cost_impact` or `financial_impact` key. When we read legacy rows,
# map the combined value onto `pnl_impact` so the modal still shows something
# (older bills will have 0 in the split capital_cost row until re-scored).
_BREAKDOWN_ALIASES = {"financial_impact": "pnl_impact"}


def _canonicalize_breakdown(data):
    if not isinstance(data, dict):
        return data
    return {_BREAKDOWN_ALIASES.get(k, k): v for k, v in data.items()}


DIRECTION_LABELS = {
    # Three directions only — framed from the MF owner-operator lens. A bill
    # that's truly "neutral" for MF owners wouldn't have cleared Stage-1
    # CRE-relevance, so there's no neutral bucket here.
    "favorable": ("Favorable for MF owners", "▲", "dir-favorable"),
    "adverse":   ("Adverse for MF owners",   "▼", "dir-adverse"),
    "mixed":     ("Mixed impact for MF",     "◆", "dir-mixed"),
}


def build_risk_summary(score, direction=None, rationale=None):
    """Scorecard row: medallion + composite-score header + one-line direction
    rationale + direction badge. Rationale sits inside the row rather than
    floating below it."""
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

    center_children = [
        html.Div("Composite impact score", className="risk-summary-title"),
    ]
    if rationale:
        center_children.append(html.Div(rationale, className="risk-summary-rationale"))
    else:
        center_children.append(html.Div(
            "Total impact magnitude on a 0–100 scale, summed from the five components below.",
            className="risk-summary-rationale"))

    return html.Div(
        [
            html.Div([html.Span(value, className="value"), html.Span("/ 100", className="suffix")],
                     className="risk-summary-score"),
            html.Div(center_children, className="risk-summary-center"),
            dir_badge,
        ],
        className="risk-summary-row",
    )


SUMMARY_SECTIONS = [
    ("what_it_does",  "What it does"),
    ("mf_impact",     "How it affects MF operators"),
    ("coverage",      "Coverage"),
    ("timing",        "Timing"),
    ("penalties",     "Penalties / remedies"),
    ("prior_law",     "Prior-law context"),
]


def _coerce_summary(summary):
    """Return a {key: paragraph} dict. Accepts either a dict (new structured
    format) or a legacy markdown string with `### Heading` blocks."""
    if isinstance(summary, dict):
        return summary
    if not isinstance(summary, str) or not summary.strip():
        return None
    # Try JSON first — some enricher runs emit a JSON string.
    s = summary.strip()
    if s.startswith("{"):
        try:
            parsed = json.loads(s)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
        # Fallback: agent may have written Python dict repr (single quotes)
        # instead of JSON (double quotes). ast.literal_eval handles both.
        try:
            import ast
            parsed = ast.literal_eval(s)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
    # Legacy markdown: split on `### Heading` lines.
    import re
    parts = re.split(r"^###\s+(.+?)\s*$", s, flags=re.MULTILINE)
    # parts = [preamble, h1, body1, h2, body2, ...]
    if len(parts) < 3:
        return {"what_it_does": s}
    heading_to_key = {
        "what it does": "what_it_does",
        "how it affects mf operators": "mf_impact",
        "how it affects mf": "mf_impact",
        "mf impact": "mf_impact",
        "coverage": "coverage",
        "timing": "timing",
        "penalties / remedies": "penalties",
        "penalties": "penalties",
        "prior-law context": "prior_law",
        "prior law context": "prior_law",
        "prior law": "prior_law",
    }
    out = {}
    for i in range(1, len(parts), 2):
        heading = parts[i].strip().lower()
        body = parts[i + 1].strip() if i + 1 < len(parts) else ""
        key = heading_to_key.get(heading)
        if key and body:
            out[key] = body
    return out or {"what_it_does": s}


def build_summary_sections(summary):
    """Render the AI summary as a list of section blocks. The UI owns the
    heading styling (not the AI) so section titles stay sized consistently
    with the rest of the modal."""
    data = _coerce_summary(summary)
    if not data:
        return html.Div(
            "AI summary pending — this bill has not yet been enriched.",
            style={"fontSize": "12px", "color": GRAY_500, "fontStyle": "italic"},
        )
    blocks = []
    for key, label in SUMMARY_SECTIONS:
        body = data.get(key)
        if not body:
            continue
        blocks.append(html.Div(
            [
                html.H4(label, className="summary-heading"),
                html.Div(body, className="summary-body"),
            ],
            className="summary-section",
        ))
    # Include any unexpected keys at the end so nothing is silently dropped.
    extras = [k for k in data.keys() if k not in {k for k, _ in SUMMARY_SECTIONS}]
    for key in extras:
        body = data.get(key)
        if not body:
            continue
        blocks.append(html.Div(
            [
                html.H4(key.replace("_", " ").title(), className="summary-heading"),
                html.Div(body, className="summary-body"),
            ],
            className="summary-section",
        ))
    return html.Div(blocks, className="summary-sections")


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
    data = _canonicalize_breakdown(data)
    rationales = _canonicalize_breakdown(rationales)

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
    {"field": "name", "headerName": "Name", "flex": 2, "minWidth": 180},
    {"field": "party", "headerName": "Party", "width": 80},
    {"field": "role", "headerName": "Role", "flex": 1, "minWidth": 140},
]


VOTE_COLUMNS = [
    {"field": "chamber", "headerName": "Chamber", "width": 90},
    {"field": "date", "headerName": "Date", "width": 100, "sort": "desc"},
    {"field": "desc", "headerName": "Vote on", "flex": 2, "minWidth": 200,
     "wrapText": True, "autoHeight": True},
    {"field": "yea", "headerName": "Yea", "width": 70,
     "cellStyle": {"color": "#059669", "fontWeight": "600"}},
    {"field": "nay", "headerName": "Nay", "width": 70,
     "cellStyle": {"color": "#dc2626", "fontWeight": "600"}},
    {"field": "other", "headerName": "NV / Abs", "width": 90},
    {"field": "result", "headerName": "Result", "flex": 1, "minWidth": 110,
     "cellStyle": {"function":
                    "params.value === 'Passed' ? {color:'#059669', fontWeight:'600'} : "
                    "params.value === 'Failed' || params.value === 'Vetoed' ? {color:'#dc2626', fontWeight:'600'} : null"}},
]


def build_votes_section(votes):
    """Renders the voting tallies section — hidden entirely when there are no
    recorded votes (introduced/in-committee bills)."""
    import dash_ag_grid as dag
    from dash import html
    if not votes:
        return html.Div()  # empty placeholder
    return html.Div(
        [
            html.Div("Voting record", className="modal-section-heading"),
            dag.AgGrid(
                id="detail-votes-grid",
                columnDefs=VOTE_COLUMNS,
                rowData=votes,
                defaultColDef={"sortable": True, "resizable": True},
                className="ag-theme-alpine",
                style={"width": "100%"},
                dashGridOptions={"domLayout": "autoHeight"},
            ),
        ]
    )


HISTORY_COLUMNS = [
    {"field": "date", "headerName": "Date", "width": 110, "sort": "desc"},
    {"field": "event_type", "headerName": "Action", "flex": 1, "minWidth": 160},
    {"field": "chamber", "headerName": "Chamber", "width": 110},
]


_EVENT_LABEL = {
    "introduced":     "Introduced",
    "in_committee":   "In committee",
    "committee":      "Reported from committee",
    "amended":        "Amended",
    "passed_chamber": "Passed chamber",
    "passed":         "Passed both chambers",
    "signed":         "Became law",
    "enacted":        "Became law",
    "vetoed":         "Killed (vetoed)",
    "failed":         "Killed (died / PI'd)",
}


def build_history_section(events):
    """Chronological bill history rendered exactly as LegiScan logged it.
    `action_text` is the raw action string from the legislature's own history
    feed ("House Second Reading Passed with Amendments - Committee",
    "Signed by Governor", etc.) — no bucketing, no collapsing."""
    import dash_ag_grid as dag
    from dash import html
    if not events:
        return html.Div()
    rows = []
    for e in events:
        action = e.get("action_text")
        if not action or str(action).strip().lower() in ("nan", "none", ""):
            etype = e.get("event_type") or ""
            action = _EVENT_LABEL.get(etype, etype.replace("_", " ").title())
        rows.append({
            "date": str(e.get("date") or "")[:10],
            "event_type": str(action),
            "chamber": (e.get("chamber") or "").title() if e.get("chamber") else "—",
        })
    rows.sort(key=lambda r: r["date"], reverse=True)
    return html.Div(
        [
            html.Div("Bill history", className="modal-section-heading"),
            dag.AgGrid(
                id="detail-history-grid",
                columnDefs=HISTORY_COLUMNS,
                rowData=rows,
                defaultColDef={"sortable": True, "resizable": True},
                className="ag-theme-alpine",
                style={"width": "100%"},
                dashGridOptions={"domLayout": "autoHeight"},
            ),
        ]
    )


def build_detail_modal():
    return dbc.Modal(
        [
            dbc.ModalHeader(dbc.ModalTitle(id="detail-title", className="modal-title")),
            dbc.ModalBody(
                [
                    html.Div(id="detail-meta",
                              style={"color": GRAY_500, "marginBottom": "12px", "fontSize": "12px"}),

                    # Composite score + direction + one-line direction rationale —
                    # all inside a single scorecard row at the top of the modal.
                    html.Div(id="detail-risk-summary"),

                    html.Div("AI summary", className="modal-section-heading",
                              style={"marginTop": "14px"}),
                    html.Div(id="detail-summary"),

                    html.Div("Impact breakdown", className="modal-section-heading"),
                    html.Div(id="detail-risk-breakdown"),

                    html.Div("Sponsors", className="modal-section-heading"),
                    dag.AgGrid(
                        id="detail-sponsors-grid",
                        columnDefs=SPONSOR_COLUMNS,
                        rowData=[],
                        defaultColDef={"sortable": True, "resizable": True},
                        className="ag-theme-alpine",
                        style={"width": "100%"},
                        dashGridOptions={"domLayout": "autoHeight"},
                    ),

                    html.Div(id="detail-history"),

                    html.Div(id="detail-votes"),

                    html.Div("Categories", className="modal-section-heading"),
                    html.Div(id="detail-subjects"),
                ]
            ),
            dbc.ModalFooter(
                [
                    dbc.Button(
                        [html.I(className="bi bi-box-arrow-up-right", style={"marginRight": "6px"}), "View on state site"],
                        id="detail-statelink-btn",
                        color="primary",
                        outline=True,
                        href="#",
                        external_link=True,
                        target="_blank",
                        disabled=True,
                    ),
                    dbc.Button(
                        [html.I(className="bi bi-file-earmark-pdf", style={"marginRight": "6px"}), "Download full text"],
                        id="detail-download-btn",
                        color="primary",
                        href="#",
                        external_link=True,
                        target="_blank",
                        disabled=True,
                        className="ms-2",
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
