"""
Click on a timeline card or bill grid row → open the detail modal.
"""

import json
import logging

from dash import Input, Output, State, callback, ctx, no_update, html, ALL
import dash_bootstrap_components as dbc

from components.detail_modal import build_risk_gauge, build_breakdown_chart
from loaders.bills import get_bill
from services.storage import signed_bill_text_url
from config import ACCENT_COLOR

logger = logging.getLogger(__name__)


@callback(
    Output("detail-modal", "is_open"),
    Output("detail-title", "children"),
    Output("detail-meta", "children"),
    Output("detail-risk-gauge", "figure"),
    Output("detail-risk-breakdown", "figure"),
    Output("detail-summary", "children"),
    Output("detail-sponsors-grid", "rowData"),
    Output("detail-subjects", "children"),
    Output("detail-download-btn", "href"),
    Output("detail-download-btn", "disabled"),
    Output("selected-bill-store", "data"),
    Input({"type": "bill-card", "bill_id": ALL}, "n_clicks"),
    Input("bill-grid", "selectedRows"),
    Input("detail-close-btn", "n_clicks"),
    State("detail-modal", "is_open"),
    prevent_initial_call=True,
)
def open_detail(card_clicks, selected_rows, close_n, is_open):
    trigger = ctx.triggered_id

    if trigger == "detail-close-btn":
        return (False,) + (no_update,) * 9 + (None,)

    bill_id = None
    if isinstance(trigger, dict) and trigger.get("type") == "bill-card":
        # Only fire when the clicked card actually has n_clicks > 0
        clicked = ctx.triggered[0] if ctx.triggered else None
        if clicked and clicked.get("value"):
            bill_id = trigger["bill_id"]
    elif trigger == "bill-grid" and selected_rows:
        bill_id = selected_rows[0].get("bill_id")

    if not bill_id:
        return (no_update,) * 11

    bill = get_bill(bill_id)
    if not bill:
        logger.warning("Bill not found: %s", bill_id)
        return (no_update,) * 11

    title = f"{bill.get('state','')} {bill.get('bill_number','')} — {bill.get('title','')}"

    meta_parts = []
    if bill.get("jurisdiction_name"):
        meta_parts.append(bill["jurisdiction_name"])
    if bill.get("session"):
        meta_parts.append(f"Session {bill['session']}")
    if bill.get("current_status"):
        meta_parts.append(f"Status: {bill['current_status']}")
    meta = " · ".join(meta_parts)

    score = bill.get("ai_risk_score")
    gauge = build_risk_gauge(score)
    breakdown = build_breakdown_chart(bill.get("ai_risk_breakdown_json"))

    summary = bill.get("ai_summary") or "_AI summary pending — this bill has not yet been enriched._"

    try:
        sponsors = json.loads(bill.get("sponsors_json")) if isinstance(bill.get("sponsors_json"), str) else (bill.get("sponsors_json") or [])
    except Exception:
        sponsors = []

    try:
        subjects = json.loads(bill.get("subjects_json")) if isinstance(bill.get("subjects_json"), str) else (bill.get("subjects_json") or [])
    except Exception:
        subjects = []
    subject_pills = [
        dbc.Badge(s.replace("_", " ").title(), color="primary", pill=True,
                  style={"marginRight": "4px", "backgroundColor": ACCENT_COLOR})
        for s in subjects
    ]

    text_path = bill.get("text_blob_path")
    download_url = signed_bill_text_url(text_path) if text_path else None
    disabled = download_url is None

    return (True, title, meta, gauge, breakdown, summary, sponsors,
            html.Div(subject_pills), download_url or "#", disabled, bill_id)
