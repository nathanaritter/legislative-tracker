"""
Card-based timeline modelled on the Milestone regulatory deck (see PPTX reference:
`Desktop/update timeline/Regulatory Update Summary CO v4.pptx`).

The timeline is rendered as absolute-positioned HTML elements on a canvas:

    . . . . . . . . . [bill card]
                          |  (connector)
    ======================●==================   axis (dots = status color)
                                       |
                                   [bill card]

Each bill occupies a slot at x = fraction of the date range, and rows cycle
through 4 slots (two above, two below) to avoid overlap. Cards carry their
bill_id in a pattern-matching callback so clicks open the detail modal.

The implementation intentionally avoids Plotly — the card visual is too specific
to fake with go.Bar / go.Scatter and the HTML approach gives pixel-perfect
parity with the PPTX.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from datetime import datetime, date
from typing import Iterable

import pandas as pd
from dash import html

from config import STATUS_COLOR, GRAY_500


# --- Layout parameters (keep in sync with styles.css .timeline-canvas etc.) ---
CANVAS_HEIGHT = 820
AXIS_Y = 400
CARD_W = 210
CARD_H = 150
ROW_GAP = 10
# Six stacking rows — three above, three below.
# (top_px, anchor_side). Height is always CARD_H.
ROWS = [
    (10,  "above_far"),
    (170, "above_mid"),
    (330, "above_near"),
    (420, "below_near"),
    (580, "below_mid"),
    (740, "below_far"),
]
MIN_CANVAS_WIDTH = 1400
MARGIN_X = 36
PIXELS_PER_DAY_TARGET = 5.2


@dataclass
class Placement:
    bill_id: str
    x_px: int
    row: int   # index into ROWS


def _status_color(status: str) -> str:
    return STATUS_COLOR.get(status, "#6A4C93")


def _short_title(title: str, n: int = 52) -> str:
    if not title:
        return ""
    title = str(title).strip()
    return title if len(title) <= n else title[: n - 1] + "…"


def _summary_to_bullets(summary: str, max_bullets: int = 3, max_chars: int = 110) -> list[str]:
    if not summary:
        return []
    # Prefer explicit bullets / newlines; fall back to sentence split.
    lines = [l.strip(" -•\t") for l in str(summary).split("\n") if l.strip()]
    if len(lines) <= 1:
        parts = [p.strip() for p in str(summary).split(". ") if p.strip()]
        lines = [p.rstrip(".") for p in parts]
    cleaned = []
    for line in lines:
        if not line:
            continue
        line = line if len(line) <= max_chars else line[: max_chars - 1] + "…"
        cleaned.append(line)
        if len(cleaned) >= max_bullets:
            break
    return cleaned


def _pack_rows(bills: pd.DataFrame, x_px_by_id: dict[str, int], min_gap: int = CARD_W + 12) -> list[Placement]:
    """Greedy row assignment: for each bill (sorted by date), place in the first row
    whose last-placed card ends ≥ min_gap before this bill's x.
    """
    placements: list[Placement] = []
    row_last_x: list[int] = [-10_000] * len(ROWS)
    for _, row in bills.iterrows():
        bill_id = row["bill_id"]
        x = x_px_by_id[bill_id]
        chosen = None
        for idx, last in enumerate(row_last_x):
            if x - last >= min_gap:
                chosen = idx
                break
        if chosen is None:
            # Last resort: place in the row with the oldest last-placed x
            chosen = min(range(len(row_last_x)), key=lambda i: row_last_x[i])
        row_last_x[chosen] = x
        placements.append(Placement(bill_id=bill_id, x_px=x, row=chosen))
    return placements


def _tick_positions(d_min: pd.Timestamp, d_max: pd.Timestamp, canvas_w: int) -> list[tuple[str, int, bool]]:
    """Return list of (label, x_px, is_major) for axis ticks.
    Major ticks = year starts. Minor ticks = month starts when zoomed in enough.
    """
    total_days = max(1, (d_max - d_min).days)
    span_years = (d_max.year - d_min.year) + 1
    show_months = span_years <= 3

    ticks: list[tuple[str, int, bool]] = []
    cursor = pd.Timestamp(d_min.year, 1, 1)
    while cursor <= d_max:
        frac = (cursor - d_min).days / total_days
        x = MARGIN_X + int(frac * (canvas_w - 2 * MARGIN_X))
        if cursor >= d_min:
            ticks.append((str(cursor.year), x, True))
        # advance to next January 1
        cursor = pd.Timestamp(cursor.year + 1, 1, 1)

    if show_months:
        cursor = pd.Timestamp(d_min.year, d_min.month, 1)
        while cursor <= d_max:
            if cursor.month != 1 and cursor >= d_min:
                frac = (cursor - d_min).days / total_days
                x = MARGIN_X + int(frac * (canvas_w - 2 * MARGIN_X))
                ticks.append((cursor.strftime("%b"), x, False))
            # advance one month
            nm = cursor.month + 1
            ny = cursor.year + (1 if nm > 12 else 0)
            nm = 1 if nm > 12 else nm
            cursor = pd.Timestamp(ny, nm, 1)

    return ticks


def _card(bill: dict, top: int, left: int) -> html.Div:
    status = bill.get("current_status") or "introduced"
    color = _status_color(status)

    date_val = bill.get("last_action_date") or bill.get("introduced_date")
    try:
        date_str = pd.to_datetime(date_val).strftime("%b %d, %Y")
    except Exception:
        date_str = ""

    bullets = _summary_to_bullets(bill.get("ai_summary", ""))
    if not bullets:
        # fall back to a short title-based line when AI hasn't run yet
        desc = _short_title(bill.get("title", ""), 200)
        if desc:
            bullets = [desc]

    score = bill.get("ai_risk_score")
    try:
        score_num = float(score) if score is not None and not pd.isna(score) else None
    except Exception:
        score_num = None
    if score_num is None:
        badge = html.Span("—", className="risk-badge risk-low", style={"background": "#9ca3af"})
    elif score_num < 40:
        badge = html.Span(f"{score_num:.0f}", className="risk-badge risk-low")
    elif score_num < 70:
        badge = html.Span(f"{score_num:.0f}", className="risk-badge risk-mid")
    else:
        badge = html.Span(f"{score_num:.0f}", className="risk-badge risk-high")

    state_label = f"{bill.get('state','')} · {bill.get('jurisdiction_name','')}".strip(" ·")

    return html.Div(
        [
            html.Div(
                [
                    html.Span(bill.get("bill_number", "")),
                    html.Span(date_str, className="date"),
                ],
                className="header",
                style={"background": color},
            ),
            html.Div(
                _short_title(bill.get("title", ""), 72),
                className="subtitle",
                style={"color": color},
            ),
            html.Div(
                [html.Div(f"• {b}", style={"marginBottom": "2px"}) for b in bullets]
                if bullets
                else html.Span("Summary pending", style={"color": GRAY_500, "fontStyle": "italic"}),
                className="body",
            ),
            html.Div(
                [
                    html.Span(state_label, style={"overflow": "hidden", "textOverflow": "ellipsis", "whiteSpace": "nowrap"}),
                    badge,
                ],
                className="footer-row",
            ),
        ],
        className="bill-card",
        id={"type": "bill-card", "bill_id": bill["bill_id"]},
        n_clicks=0,
        style={"top": f"{top}px", "left": f"{left}px"},
    )


def build_timeline_card_area():
    """Outer card + scrollable canvas. Contents are filled by the timeline callback."""
    return html.Div(
        [
            html.H5("Legislation timeline"),
            html.Div(id="timeline-meta",
                     style={"fontSize": "11px", "color": GRAY_500, "marginBottom": "10px"}),
            html.Div(
                html.Div(id="timeline-canvas", className="timeline-canvas"),
                className="timeline-wrap",
            ),
        ],
        className="card",
    )


def render_timeline(bills: pd.DataFrame) -> tuple[list, str]:
    """Return (children, meta_text) for the timeline canvas."""
    if bills is None or bills.empty:
        return (
            [html.Div("No bills match the current filters.",
                      style={"position": "absolute", "top": "48%", "left": "50%",
                              "transform": "translate(-50%, -50%)", "color": GRAY_500})],
            "0 bills",
        )

    bills = bills.copy()
    bills["_primary_date"] = pd.to_datetime(bills["last_action_date"].fillna(bills["introduced_date"]), errors="coerce")
    bills = bills.dropna(subset=["_primary_date"]).sort_values("_primary_date").reset_index(drop=True)
    if bills.empty:
        return [], "0 bills with a valid date"

    d_min, d_max = bills["_primary_date"].min(), bills["_primary_date"].max()
    # Add a month of padding on each side so cards at the edges don't get cut off.
    d_min = d_min - pd.Timedelta(days=20)
    d_max = d_max + pd.Timedelta(days=20)
    total_days = max(1, (d_max - d_min).days)

    canvas_w = max(MIN_CANVAS_WIDTH, int(total_days * PIXELS_PER_DAY_TARGET))
    usable_w = canvas_w - 2 * MARGIN_X

    x_px_by_id: dict[str, int] = {}
    for _, row in bills.iterrows():
        frac = (row["_primary_date"] - d_min).days / total_days
        x_px_by_id[row["bill_id"]] = MARGIN_X + int(frac * usable_w)

    placements = _pack_rows(bills, x_px_by_id)

    children: list = []

    # Axis line
    children.append(html.Div(className="timeline-axis",
                              style={"left": f"{MARGIN_X}px", "right": f"{MARGIN_X}px"}))

    # Ticks (absolute top comes from CSS; inline height distinguishes major/minor)
    for label, x, is_major in _tick_positions(d_min, d_max, canvas_w):
        children.append(html.Div(className="timeline-tick",
                                  style={"left": f"{x}px",
                                          "height": "18px" if is_major else "10px",
                                          "top": "392px" if is_major else "396px"}))
        children.append(html.Div(label, className="timeline-tick-label",
                                  style={"left": f"{x}px",
                                          "fontSize": "11px" if is_major else "10px",
                                          "fontWeight": "600" if is_major else "500",
                                          "color": GRAY_500 if not is_major else "#374151"}))

    # Cards + dots + connectors
    bills_by_id = {r["bill_id"]: r for _, r in bills.iterrows()}
    for p in placements:
        bill = bills_by_id[p.bill_id].to_dict() if hasattr(bills_by_id[p.bill_id], "to_dict") else bills_by_id[p.bill_id]
        color = _status_color(bill.get("current_status") or "introduced")
        row_top, anchor = ROWS[p.row]

        # Card
        children.append(_card(bill, top=row_top, left=p.x_px - CARD_W // 2))

        # Axis dot
        children.append(html.Div(className="timeline-dot",
                                  style={"left": f"{p.x_px}px", "top": f"{AXIS_Y}px",
                                          "background": color}))

        # Connector line from axis to card
        if anchor.startswith("above"):
            top = row_top + CARD_H
            height = AXIS_Y - top
            y = top
        else:
            top = AXIS_Y
            height = row_top - AXIS_Y
            y = top
        if height > 0:
            children.append(html.Div(className="timeline-connector",
                                      style={"left": f"{p.x_px}px",
                                              "top": f"{y}px",
                                              "height": f"{height}px",
                                              "background": color}))

    meta = f"{len(bills)} bills · {d_min.strftime('%b %Y')} – {d_max.strftime('%b %Y')}"
    return children, meta


def canvas_style_for(bills: pd.DataFrame) -> dict:
    """Width override for the timeline canvas based on current date range."""
    if bills is None or bills.empty:
        return {"minWidth": f"{MIN_CANVAS_WIDTH}px"}
    d_min = pd.to_datetime(bills["introduced_date"], errors="coerce").min()
    d_max = pd.to_datetime(bills["last_action_date"], errors="coerce").max()
    try:
        days = max(1, (d_max - d_min).days)
    except Exception:
        return {"minWidth": f"{MIN_CANVAS_WIDTH}px"}
    w = max(MIN_CANVAS_WIDTH, int(days * PIXELS_PER_DAY_TARGET))
    return {"minWidth": f"{w}px", "width": f"{w}px"}
