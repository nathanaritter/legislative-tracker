"""
Click on a timeline card or bill grid row → open the detail modal.
"""

import json
import logging

import pandas as pd
from dash import Input, Output, State, callback, ctx, no_update, html, ALL
import dash_bootstrap_components as dbc


def _str_or_none(v):
    """Return v as a clean string, or None if NaN / empty. Pandas returns
    `nan` (float) for missing string cells, which is truthy and breaks `or ""`
    fallbacks."""
    if v is None:
        return None
    if isinstance(v, float) and pd.isna(v):
        return None
    s = str(v).strip()
    return s or None

from components.detail_modal import (build_risk_summary, build_breakdown,
                                      build_summary_sections,
                                      build_votes_section, build_history_section)
from loaders.bills import get_bill, load_events
from services.storage import signed_bill_text_url
from config import ACCENT_COLOR, STATUS_LABEL, CATEGORY_LABEL

logger = logging.getLogger(__name__)


@callback(
    Output("detail-modal", "is_open"),
    Output("detail-title", "children"),
    Output("detail-meta", "children"),
    Output("detail-risk-summary", "children"),
    Output("detail-risk-breakdown", "children"),
    Output("detail-summary", "children"),
    Output("detail-sponsors-grid", "rowData"),
    Output("detail-history", "children"),
    Output("detail-votes", "children"),
    Output("detail-subjects", "children"),
    Output("detail-statelink-btn", "href"),
    Output("detail-statelink-btn", "disabled"),
    Output("detail-download-btn", "href"),
    Output("detail-download-btn", "disabled"),
    Output("selected-bill-store", "data"),
    Input({"type": "bill-card", "bill_id": ALL, "event": ALL, "date": ALL}, "n_clicks"),
    Input({"type": "bill-legend-label", "bill_id": ALL}, "n_clicks"),
    Input("detail-close-btn", "n_clicks"),
    State("detail-modal", "is_open"),
    prevent_initial_call=True,
)
def open_detail(card_clicks, legend_label_clicks, close_n, is_open):
    trigger = ctx.triggered_id
    N_OUT = 15  # total outputs including selected-bill-store

    if trigger == "detail-close-btn":
        return (False,) + (no_update,) * (N_OUT - 2) + (None,)

    bill_id = None
    if isinstance(trigger, dict) and trigger.get("type") in ("bill-card", "bill-legend-label"):
        clicked = ctx.triggered[0] if ctx.triggered else None
        if clicked and clicked.get("value"):
            bill_id = trigger["bill_id"]

    if not bill_id:
        return (no_update,) * N_OUT

    bill = get_bill(bill_id)
    if not bill:
        logger.warning("Bill not found: %s", bill_id)
        return (no_update,) * N_OUT

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
    direction_rationale = _str_or_none(bill.get("ai_direction_rationale")) or ""
    summary_block = build_risk_summary(
        score,
        _str_or_none(bill.get("impact_direction")) or "",
        rationale=direction_rationale,
    )
    breakdown_block = build_breakdown(
        _str_or_none(bill.get("ai_risk_breakdown_json")),
        _str_or_none(bill.get("ai_risk_rationale_json")),
    )

    summary_block_sections = build_summary_sections(_str_or_none(bill.get("ai_summary")))

    try:
        sponsors_raw = _str_or_none(bill.get("sponsors_json"))
        sponsors_all = json.loads(sponsors_raw) if sponsors_raw else []
    except Exception:
        sponsors_all = []
    # Prime sponsors only. LegiScan marks primes with sponsor_order 1 (or 0
    # occasionally). Cosponsors flood the grid and don't help the user — they
    # want to know who's actually driving the bill. Fall back to the first 2
    # if no order field is present.
    def _is_prime(s):
        o = s.get("sponsor_order")
        return str(o) in ("0", "1") or o in (0, 1)
    primes = [s for s in sponsors_all if _is_prime(s)]
    if not primes:
        primes = sponsors_all[:2]
    sponsors = [
        {"name":  s.get("name") or "",
          "party": s.get("party") or "",
          "role":  s.get("role") or "Prime"}
        for s in primes
    ]

    try:
        votes_raw_s = _str_or_none(bill.get("votes_json"))
        votes_raw = json.loads(votes_raw_s) if votes_raw_s else []
    except Exception:
        votes_raw = []
    votes = []
    for v in votes_raw:
        yea = int(v.get("yea", 0) or 0)
        nay = int(v.get("nay", 0) or 0)
        nv = int(v.get("nv", 0) or 0)
        absent = int(v.get("absent", 0) or 0)
        desc = v.get("desc") or ""
        # Strip HTML entities LegiScan sometimes leaves in vote descriptions.
        desc = desc.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
        votes.append({
            "chamber": v.get("chamber") or "",
            "date": v.get("date") or "",
            "desc": desc,
            "yea": yea,
            "nay": nay,
            "other": f"{nv} / {absent}" if (nv or absent) else "—",
            "result": v.get("result") or ("Passed" if (yea > nay and v.get("passed")) else "Failed"),
        })
    votes_section = build_votes_section(votes)

    # Modal shows AI-assigned categories (not LegiScan raw subjects). These
    # are the same tags that populate the Category filter in the sidebar.
    try:
        cat_raw = _str_or_none(bill.get("ai_categories"))
        categories = json.loads(cat_raw) if cat_raw else []
        if not isinstance(categories, list):
            categories = [categories]
    except Exception:
        categories = []
    subject_pills = [
        dbc.Badge(
            CATEGORY_LABEL.get(str(c), str(c).replace("_", " ").title()),
            color="primary", pill=True,
            style={"marginRight": "4px", "backgroundColor": ACCENT_COLOR},
        )
        for c in categories if c
    ]

    # Bill history (chronological actions from bill_events.csv)
    events_df = load_events()
    hist_rows = []
    if events_df is not None and not events_df.empty:
        m = events_df[events_df["bill_id"] == bill_id].sort_values("date")
        for _, ev in m.iterrows():
            hist_rows.append({
                "date": ev.get("date"),
                "event_type": ev.get("event_type"),
                "chamber": ev.get("chamber"),
                "action_text": ev.get("action_text") if "action_text" in ev.index else None,
            })
    history_section = build_history_section(hist_rows)

    text_path = _str_or_none(bill.get("text_blob_path"))
    download_url = None
    if text_path and text_path.startswith("legislation/"):
        download_url = signed_bill_text_url(text_path)
    download_disabled = download_url is None

    state_url = _str_or_none(bill.get("url")) or ""
    state_disabled = not state_url

    return (True, title, meta, summary_block, breakdown_block,
            summary_block_sections, sponsors,
            history_section, votes_section, html.Div(subject_pills),
            state_url or "#", state_disabled,
            download_url or "#", download_disabled,
            bill_id)
