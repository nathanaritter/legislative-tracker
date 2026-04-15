"""
Click on a timeline card or bill grid row → open the detail modal.
"""

import json
import logging

from dash import Input, Output, State, callback, ctx, no_update, html, ALL
import dash_bootstrap_components as dbc

from components.detail_modal import build_risk_summary, build_breakdown
from loaders.bills import get_bill
from services.storage import signed_bill_text_url
from config import ACCENT_COLOR, STATUS_LABEL

logger = logging.getLogger(__name__)


@callback(
    Output("detail-modal", "is_open"),
    Output("detail-title", "children"),
    Output("detail-meta", "children"),
    Output("detail-risk-summary", "children"),
    Output("detail-risk-breakdown", "children"),
    Output("detail-summary", "children"),
    Output("detail-sponsors-grid", "rowData"),
    Output("detail-subjects", "children"),
    Output("detail-download-btn", "href"),
    Output("detail-download-btn", "disabled"),
    Output("selected-bill-store", "data"),
    Input({"type": "bill-card", "bill_id": ALL, "event": ALL, "date": ALL}, "n_clicks"),
    Input("detail-close-btn", "n_clicks"),
    State("detail-modal", "is_open"),
    prevent_initial_call=True,
)
def open_detail(card_clicks, close_n, is_open):
    trigger = ctx.triggered_id

    if trigger == "detail-close-btn":
        return (False,) + (no_update,) * 9 + (None,)

    bill_id = None
    if isinstance(trigger, dict) and trigger.get("type") == "bill-card":
        clicked = ctx.triggered[0] if ctx.triggered else None
        if clicked and clicked.get("value"):
            bill_id = trigger["bill_id"]

    if not bill_id:
        return (no_update,) * 11

    bill = get_bill(bill_id)
    if not bill:
        logger.warning("Bill not found: %s", bill_id)
        return (no_update,) * 11

    title = f"{bill.get('bill_number','')} — {bill.get('title','')}"

    meta_parts = []
    if bill.get("jurisdiction_name"):
        meta_parts.append(bill["jurisdiction_name"])
    if bill.get("session") and bill.get("session") != "Demo session":
        meta_parts.append(f"Session {bill['session']}")
    status_raw = bill.get("current_status") or ""
    if status_raw:
        meta_parts.append(f"Status: {STATUS_LABEL.get(status_raw, status_raw.replace('_', ' ').title())}")
    meta = " · ".join(meta_parts)

    score = bill.get("ai_risk_score")
    summary_block = build_risk_summary(score, bill.get("impact_direction"))
    breakdown_block = build_breakdown(
        bill.get("ai_risk_breakdown_json"),
        bill.get("ai_risk_rationale_json"),
    )

    summary_text = bill.get("ai_summary") or "_AI summary pending — this bill has not yet been enriched._"

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

    return (True, title, meta, summary_block, breakdown_block, summary_text, sponsors,
            html.Div(subject_pills), download_url or "#", disabled, bill_id)
