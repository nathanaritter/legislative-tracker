"""
Card-based timeline where **every stage of every bill** is its own card.

A bill that moves Introduced → Committee → Passed → Enacted renders as 4 cards
on the timeline, each at the date of that stage transition. Clicking any card
opens the detail modal for the parent bill.

Each card is colored by the stage bucket and shows:
  - stage name + date in the header (the "date means" the stage date)
  - bill number + short title in the body
  - jurisdiction
  - risk chip
"""

from __future__ import annotations

from dataclasses import dataclass
import json

import pandas as pd
from dash import html

from config import STATUS_GROUP, STAGE_LABELS, GRAY_500


# Canvas / row geometry — card height 96, rows spaced 110 apart so the card
# bottoms clear the axis with a visible connector line. Rows alternate above /
# below; more rows = taller canvas, which the wrap scrolls vertically.
AXIS_Y = 380
CARD_W = 188
CARD_H = 96
MIN_CANVAS_WIDTH = 1400
MARGIN_X = 110
PIXELS_PER_DAY_TARGET = 5.2
MAX_CANVAS_WIDTH = 14000

# (top_px, anchor_side). Add more pairs here to raise the stacking ceiling.
ROWS = [
    (272, "above_near"),   # bottom 368, axis at 380
    (162, "above_mid"),    # bottom 258
    (52,  "above_far"),    # bottom 148
    (400, "below_near"),
    (510, "below_mid"),
    (620, "below_far"),
    (730, "below_far2"),
    (840, "below_far3"),
]
CANVAS_HEIGHT = 940  # enough to contain all 8 rows


STAGE_COLORS = {
    "introduced": "#6A4C93",
    "committee":  "#6A4C93",
    "passed":     "#1B5E83",
    "enacted":    "#2E7D32",
    "failed":     "#999999",
}


@dataclass
class EventCard:
    bill_id: str
    event_date: pd.Timestamp
    stage_group: str     # introduced/committee/passed/enacted/failed
    raw_event_type: str
    x_px: int = 0
    row: int = 0


def _short_title(title: str, n: int = 50) -> str:
    if not title:
        return ""
    title = str(title).strip()
    return title if len(title) <= n else title[: n - 1] + "…"


def _pack_rows(cards, min_gap=CARD_W + 10):
    row_last = [-10_000] * len(ROWS)
    dropped = 0
    for c in cards:
        chosen = None
        for i, last in enumerate(row_last):
            if c.x_px - last >= min_gap:
                chosen = i
                break
        if chosen is None:
            dropped += 1
            c.row = -1
            continue
        row_last[chosen] = c.x_px
        c.row = chosen
    return [c for c in cards if c.row >= 0], dropped


def _density_min_width(event_dates, d_min, d_max, min_gap=CARD_W + 10, rows=len(ROWS)):
    """Minimum canvas width such that the densest min_gap-wide window holds no
    more cards than we have rows. Used as a floor when zooming out."""
    total_days = max(1, (d_max - d_min).days)
    canvas_w = max(MIN_CANVAS_WIDTH, int(total_days * PIXELS_PER_DAY_TARGET))
    dates = sorted(event_dates) if event_dates else []
    if not dates or len(dates) <= rows:
        return canvas_w
    for _ in range(8):
        usable = canvas_w - 2 * MARGIN_X
        px_per_day = usable / total_days
        window_days = min_gap / px_per_day if px_per_day else total_days
        max_cluster = 1
        j = 0
        for i in range(len(dates)):
            if j < i:
                j = i
            while j < len(dates) and (dates[j] - dates[i]).days < window_days:
                j += 1
            max_cluster = max(max_cluster, j - i)
        if max_cluster <= rows:
            return canvas_w
        canvas_w = int(canvas_w * (max_cluster / rows))
    return canvas_w


def _canvas_width_for(event_dates, d_min, d_max, min_gap=CARD_W + 10, rows=len(ROWS), zoom=1.0):
    """Canvas width honoring (a) the density floor (zoom-out can't make cards
    overlap beyond the row budget) and (b) the caller-supplied zoom multiplier.

    zoom > 1: canvas grows proportionally (zoom-in).
    zoom < 1: canvas shrinks but not below the density floor (zoom-out stops
               once the densest window already fills all rows).
    """
    total_days = max(1, (d_max - d_min).days)
    base_w = max(MIN_CANVAS_WIDTH, int(total_days * PIXELS_PER_DAY_TARGET))
    density_min = _density_min_width(event_dates, d_min, d_max, min_gap=min_gap, rows=rows)
    # "Fit" width = whichever of (time span, density requirement) is larger.
    # Zoom multiplies the fit; density floor still applies so zoom-out never
    # collapses cards into each other.
    fit = max(base_w, density_min)
    final = max(int(fit * zoom), density_min)
    return int(min(final, MAX_CANVAS_WIDTH * 4))


def _tick_positions(d_min, d_max, canvas_w):
    total_days = max(1, (d_max - d_min).days)
    span_years = (d_max.year - d_min.year) + 1
    show_months = span_years <= 3
    usable = canvas_w - 2 * MARGIN_X
    ticks = []
    cursor = pd.Timestamp(d_min.year, 1, 1)
    while cursor <= d_max:
        frac = (cursor - d_min).days / total_days
        x = MARGIN_X + int(frac * usable)
        if cursor >= d_min:
            ticks.append((str(cursor.year), x, True))
        cursor = pd.Timestamp(cursor.year + 1, 1, 1)
    if show_months:
        cursor = pd.Timestamp(d_min.year, d_min.month, 1)
        while cursor <= d_max:
            if cursor.month != 1 and cursor >= d_min:
                frac = (cursor - d_min).days / total_days
                x = MARGIN_X + int(frac * usable)
                ticks.append((cursor.strftime("%b"), x, False))
            nm = cursor.month + 1
            ny = cursor.year + (1 if nm > 12 else 0)
            nm = 1 if nm > 12 else nm
            cursor = pd.Timestamp(ny, nm, 1)
    return ticks


def _risk_chip(score):
    try:
        s = float(score) if score is not None and not pd.isna(score) else None
    except Exception:
        s = None
    if s is None:
        return None
    bg = "#059669" if s < 40 else "#d97706" if s < 70 else "#dc2626"
    return html.Span(f"{s:.0f}", className="risk-chip", style={"background": bg})


def _stage_card(card: EventCard, bill: dict, top: int, left: int) -> html.Div:
    color = STAGE_COLORS.get(card.stage_group, "#6A4C93")
    stage_label = STAGE_LABELS.get(card.stage_group, card.stage_group.title())
    # Short date — "Mar 06 '25" — so it fits alongside the stage chip + risk chip.
    date_str = card.event_date.strftime("%b %d '%y")
    iso_date = card.event_date.strftime("%Y-%m-%d")

    header_children = [
        html.Span(stage_label, className="stage-label"),
        html.Span(date_str, className="stage-date"),
    ]
    chip = _risk_chip_inline(bill.get("ai_risk_score"), bill.get("impact_direction"))
    if chip is not None:
        header_children.append(chip)

    children = [
        html.Div(header_children, className="header", style={"background": color}),
        html.Div(
            [
                html.Span(bill.get("bill_number", ""), className="bill-num"),
                html.Span(_short_title(bill.get("title", ""), 50), className="bill-title"),
            ],
            className="body",
        ),
        html.Div(bill.get("jurisdiction_name", ""), className="juris"),
    ]

    return html.Div(
        children,
        className="bill-card",
        id={"type": "bill-card", "bill_id": bill["bill_id"], "event": card.raw_event_type,
             "date": iso_date},
        n_clicks=0,
        style={"top": f"{top}px", "left": f"{left}px"},
        **{"data-event-date": iso_date, "data-bill-id": bill["bill_id"], "data-row": str(-1)},
    )


DIRECTION_GLYPH = {
    "favorable": "▲",
    "adverse":   "▼",
    "mixed":     "◆",
    "neutral":   "●",
}


def _risk_chip_inline(score, direction=None):
    """Small header-inline chip showing impact magnitude + direction glyph."""
    try:
        s = float(score) if score is not None and not pd.isna(score) else None
    except Exception:
        s = None
    if s is None:
        return None
    d = (direction or "").lower()
    glyph = DIRECTION_GLYPH.get(d, "")
    return html.Span(
        [html.Span(f"{s:.0f}"), html.Span(glyph, className=f"dir dir-{d or 'unk'}")],
        className="stage-score",
    )


def build_timeline_card_area():
    header_row = html.Div(
        [
            html.H5("Bill progression timeline", style={"margin": 0}),
            html.Span(
                "Drag horizontally to zoom · double-click to reset",
                className="timeline-hint",
            ),
        ],
        style={"display": "flex", "alignItems": "center", "justifyContent": "space-between",
                "marginBottom": "6px"},
    )
    return html.Div(
        [
            header_row,
            html.Div(id="timeline-meta",
                     style={"fontSize": "11px", "color": GRAY_500, "marginBottom": "8px"}),
            html.Div(
                html.Div(id="timeline-canvas", className="timeline-canvas"),
                className="timeline-wrap",
                id="timeline-wrap",
            ),
        ],
        className="card",
    )


def _collect_events(bills: pd.DataFrame, events: pd.DataFrame) -> list[EventCard]:
    """Build one EventCard per (bill, stage-bucket). Committee actions roll up
    into Intro — so if a bill has Introduced + Referred + Reported events, only
    the earliest one produces an Intro card, not three."""
    cards_raw: list[EventCard] = []
    bills_by_id = {r["bill_id"]: r for _, r in bills.iterrows()}

    if events is not None and not events.empty:
        for _, e in events.iterrows():
            bid = e["bill_id"]
            if bid not in bills_by_id:
                continue
            group = STATUS_GROUP.get(e.get("event_type") or "", None)
            if group is None:
                continue
            d = pd.to_datetime(e.get("date"), errors="coerce")
            if pd.isna(d):
                continue
            cards_raw.append(EventCard(
                bill_id=bid,
                event_date=d,
                stage_group=group,
                raw_event_type=e.get("event_type"),
            ))

    # Dedupe: keep the earliest card per (bill_id, stage_group).
    by_key: dict[tuple[str, str], EventCard] = {}
    for c in cards_raw:
        key = (c.bill_id, c.stage_group)
        if key not in by_key or c.event_date < by_key[key].event_date:
            by_key[key] = c
    cards = list(by_key.values())

    # Fallback: any bill without a single event gets an Intro card from
    # introduced_date so it still appears on the timeline.
    billed = {c.bill_id for c in cards}
    for bid, row in bills_by_id.items():
        if bid in billed:
            continue
        d = pd.to_datetime(row.get("introduced_date"), errors="coerce")
        if pd.isna(d):
            continue
        cards.append(EventCard(
            bill_id=bid,
            event_date=d,
            stage_group="introduced",
            raw_event_type="introduced",
        ))

    cards.sort(key=lambda c: c.event_date)
    return cards


def render_timeline(bills: pd.DataFrame, events: pd.DataFrame | None = None):
    zoom = 1.0  # Server renders at 100%; assets/timeline_zoom.js handles any zoom
    if bills is None or bills.empty:
        return (
            [html.Div("No bills match the current filters.",
                      style={"position": "absolute", "top": "48%", "left": "50%",
                              "transform": "translate(-50%, -50%)", "color": GRAY_500})],
            "0 bills",
        )

    cards = _collect_events(bills, events if events is not None else pd.DataFrame())
    if not cards:
        return [], "0 stage events"

    d_min = min(c.event_date for c in cards) - pd.Timedelta(days=20)
    d_max = max(c.event_date for c in cards) + pd.Timedelta(days=20)
    total_days = max(1, (d_max - d_min).days)

    canvas_w = _canvas_width_for([c.event_date for c in cards], d_min, d_max, zoom=zoom)
    usable_w = canvas_w - 2 * MARGIN_X

    for c in cards:
        frac = (c.event_date - d_min).days / total_days
        c.x_px = MARGIN_X + int(frac * usable_w)

    cards, dropped = _pack_rows(cards)

    # Hidden data div carries the pixel-to-date mapping constants so the
    # clientside drag-zoom handler can convert a drag rectangle into date bounds
    # without asking the server.
    children = [
        html.Div(
            id="timeline-bounds",
            style={"display": "none"},
            **{
                "data-d-min": d_min.strftime("%Y-%m-%d"),
                "data-d-max": d_max.strftime("%Y-%m-%d"),
                "data-margin": str(MARGIN_X),
                "data-canvas-w": str(canvas_w),
            },
        ),
        html.Div(className="timeline-axis",
                 style={"left": f"{MARGIN_X}px", "right": f"{MARGIN_X}px"}),
    ]

    for label, x, is_major in _tick_positions(d_min, d_max, canvas_w):
        children.append(html.Div(className="timeline-tick",
                                  style={"left": f"{x}px",
                                          "height": "18px" if is_major else "10px",
                                          "top": "372px" if is_major else "376px"}))
        children.append(html.Div(label, className="timeline-tick-label",
                                  style={"left": f"{x}px",
                                          "fontSize": "11px" if is_major else "10px",
                                          "fontWeight": "600" if is_major else "500"}))

    bills_by_id = {r["bill_id"]: r for _, r in bills.iterrows()}

    for c in cards:
        bill = bills_by_id[c.bill_id]
        bill_dict = bill.to_dict() if hasattr(bill, "to_dict") else bill
        color = STAGE_COLORS.get(c.stage_group, "#6A4C93")
        row_top, anchor = ROWS[c.row]

        children.append(_stage_card(c, bill_dict, top=row_top, left=c.x_px - CARD_W // 2))
        children.append(html.Div(
            className="timeline-dot",
            style={"left": f"{c.x_px}px", "top": f"{AXIS_Y}px", "background": color},
            **{"data-bill-id": c.bill_id,
               "data-event-date": c.event_date.strftime("%Y-%m-%d")},
        ))
        if anchor.startswith("above"):
            top = row_top + CARD_H
            height = AXIS_Y - top
            y = top
        else:
            top = AXIS_Y
            height = row_top - AXIS_Y
            y = top
        if height > 0:
            children.append(html.Div(
                className="timeline-connector",
                style={"left": f"{c.x_px}px",
                        "top": f"{y}px",
                        "height": f"{height}px",
                        "background": color},
                **{"data-bill-id": c.bill_id,
                   "data-event-date": c.event_date.strftime("%Y-%m-%d")},
            ))

    n_bills = len(set(c.bill_id for c in cards))
    meta = f"{len(cards)} stage events across {n_bills} bills · {d_min.strftime('%b %Y')} – {d_max.strftime('%b %Y')}"
    if dropped:
        meta += f" · {dropped} stages hidden (narrow the date range)"
    return children, meta


def canvas_bounds(bills: pd.DataFrame, events: pd.DataFrame | None = None):
    """Return (d_min_iso, d_max_iso) of the event span, or None if empty.
    Used by the clientside drag-zoom handler to translate pixel coords to dates."""
    if bills is None or bills.empty:
        return None
    cards = _collect_events(bills, events if events is not None else pd.DataFrame())
    if not cards:
        return None
    d_min = min(c.event_date for c in cards) - pd.Timedelta(days=20)
    d_max = max(c.event_date for c in cards) + pd.Timedelta(days=20)
    return d_min.strftime("%Y-%m-%d"), d_max.strftime("%Y-%m-%d")


def canvas_style_for(bills: pd.DataFrame, events: pd.DataFrame | None = None) -> dict:
    """Canvas width = density-fit (wide enough that cards don't overlap at
    default zoom). Height = CANVAS_HEIGHT so the wrap can scroll vertically
    if more stacks get added later."""
    if bills is None or bills.empty:
        return {"minWidth": f"{MIN_CANVAS_WIDTH}px", "height": f"{CANVAS_HEIGHT}px"}
    cards = _collect_events(bills, events if events is not None else pd.DataFrame())
    if not cards:
        return {"minWidth": f"{MIN_CANVAS_WIDTH}px", "height": f"{CANVAS_HEIGHT}px"}
    d_min = min(c.event_date for c in cards) - pd.Timedelta(days=20)
    d_max = max(c.event_date for c in cards) + pd.Timedelta(days=20)
    w = _canvas_width_for([c.event_date for c in cards], d_min, d_max)
    return {"width": f"{w}px", "height": f"{CANVAS_HEIGHT}px"}
