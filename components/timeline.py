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
from dash import html, dcc

from config import STATUS_GROUP, STAGE_LABELS, GRAY_500


# Canvas / row geometry — card height 96, rows spaced 110 apart so the card
# bottoms clear the axis with a visible connector line. Rows alternate above /
# below; more rows = taller canvas, which the wrap scrolls vertically.
AXIS_Y = 380
CARD_W = 188
CARD_H = 118
MIN_CANVAS_WIDTH = 700
MARGIN_X = 110
# Natural density at zoom=1. Higher density → fewer cards collide in the
# packer (fewer "stages hidden" warnings). User still uses CSS zoom to zoom in
# further when they want cards separated visually.
PIXELS_PER_DAY_TARGET = 8.0
MAX_CANVAS_WIDTH = 12000

# Past this card count the packer overflow + DOM size makes the timeline
# unusable. Show an empty state with a "narrow your filters" prompt instead.
MAX_CARDS = 600

# (top_px, anchor_side). Row packing walks this list in order, so alternating
# above/below makes them fill symmetrically instead of piling all cards above
# the axis before ever using the below-axis rows.
ROWS = [
    # Tick marks occupy y=372–390 (axis at 380), tick labels y=394–412. Cards
    # should never enter either band, so above_near bottom is ≤ 366 and
    # below_near top is ≥ 420. Row height = 130px (118 card + 12 gap).
    (230, "above_near"),
    (420, "below_near"),
    (100, "above_mid"),
    (550, "below_mid"),
    (680, "below_far1"),
    (810, "below_far2"),
    (940, "below_far3"),
    (1070, "below_far4"),
    (1200, "below_far5"),
    (1330, "below_far6"),
    (1460, "below_far7"),
    (1590, "below_far8"),
]
CANVAS_HEIGHT = 1750


STAGE_COLORS = {
    "introduced": "#6A4C93",
    "passed":     "#1B5E83",
    "law":        "#2E7D32",
    "killed":     "#999999",
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
    """Pack cards into non-overlapping rows, expanding downward below the axis
    as density demands — no card is ever dropped. ROWS is the preferred-order
    list (alternating above/below the axis, filling close-to-axis first); any
    overflow spawns extra rows below the last below_far* slot so the visual
    never sees a missing card."""
    row_last = [-10_000] * len(ROWS)
    row_defs = list(ROWS)  # working copy we can append to
    for c in cards:
        chosen = None
        for i, last in enumerate(row_last):
            if c.x_px - last >= min_gap:
                chosen = i
                break
        if chosen is None:
            # Spawn a new below-axis row beneath the lowest existing one.
            new_top = max(t for t, _ in row_defs) + 130
            row_defs.append((new_top, f"below_overflow_{len(row_defs)}"))
            row_last.append(-10_000)
            chosen = len(row_defs) - 1
        row_last[chosen] = c.x_px
        c.row = chosen
    return cards, 0, row_defs


def _canvas_width_for(event_dates, d_min, d_max, min_gap=CARD_W + 10, rows=len(ROWS), zoom=1.0):
    """Natural canvas width at zoom=1.

    Width is driven by **event count**, not date range: the whole point of
    this chart is to show cards side-by-side, so a dense month needs a wide
    canvas regardless of how few days it spans. Formula: give each event
    roughly half a card-width of horizontal real-estate so the packer can fit
    ~2 events per horizontal slot across the visible rows before having to
    spawn overflow rows.
    """
    n_events = max(1, len(list(event_dates)))
    # Per-event budget bumped to 220 so even date-clustered events (multiple
    # stages of one bill within a 30-day window) get enough horizontal room
    # for cards to lay out side-by-side instead of stacking into overflow
    # rows. Sparse dockets get a comfortable minimum; dense dockets cap.
    per_event = 220
    w = int(n_events * per_event * zoom)
    return max(MIN_CANVAS_WIDTH, min(w, MAX_CANVAS_WIDTH))


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

    children = [
        html.Div(header_children, className="header", style={"background": color}),
        html.Div(
            [
                html.Span(bill.get("bill_number", ""), className="bill-num"),
                html.Span(bill.get("title", "") or "", className="bill-title"),
            ],
            className="body",
        ),
    ]
    # Footer strip: impact score on the left, jurisdiction on the right. One
    # row so the body above gets the full vertical budget for the title.
    chip = _risk_chip_inline(bill.get("ai_risk_score"), bill.get("impact_direction"))
    footer_children = []
    if chip is not None:
        footer_children.append(chip)
    else:
        footer_children.append(html.Span("", className="stage-score-placeholder"))
    footer_children.append(html.Span(bill.get("jurisdiction_name", ""),
                                      className="card-juris"))
    children.append(html.Div(footer_children, className="card-footer"))

    return html.Div(
        children,
        className="bill-card",
        id={"type": "bill-card", "bill_id": bill["bill_id"], "event": card.raw_event_type,
             "date": iso_date},
        n_clicks=0,
        style={"top": f"{top}px", "left": f"{left}px"},
        **{"data-event-date": iso_date, "data-bill-id": bill["bill_id"],
           "data-stage-group": card.stage_group, "data-row": str(-1)},
    )


DIRECTION_GLYPH = {
    "favorable": "▲",
    "adverse":   "▼",
    "mixed":     "◆",
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
            html.Div(
                [
                    html.Span(
                        "Drag to pan · Ctrl+wheel or +/− to zoom · double-click to fit",
                        className="timeline-hint",
                        style={"marginRight": "10px"},
                    ),
                    html.Button(html.I(className="bi bi-zoom-out"),
                                id="timeline-zoom-out-btn", className="zoom-btn",
                                title="Zoom out"),
                    html.Button(html.I(className="bi bi-zoom-in"),
                                id="timeline-zoom-in-btn", className="zoom-btn",
                                title="Zoom in",
                                style={"marginLeft": "4px"}),
                    html.Button(
                        [html.I(className="bi bi-arrow-counterclockwise",
                                 style={"marginRight": "4px"}), "Reset view"],
                        id="timeline-reset-btn",
                        className="zoom-btn",
                        style={"marginLeft": "8px"},
                        title="Reset zoom to default and clear hide state",
                    ),
                ],
                style={"display": "flex", "alignItems": "center"},
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
            dcc.Loading(
                id="timeline-loading",
                type="circle",
                color="#1B5E83",
                children=html.Div(
                    html.Div(id="timeline-canvas", className="timeline-canvas"),
                    className="timeline-wrap",
                    id="timeline-wrap",
                ),
            ),
        ],
        className="card",
    )


def _collect_events(bills: pd.DataFrame, events: pd.DataFrame) -> list[EventCard]:
    """Build one EventCard per (bill, stage-bucket). Committee actions roll up
    into Intro — so if a bill has Introduced + Referred + Reported events, only
    the earliest one produces an Intro card, not three.

    LegiScan does not reliably emit an "Enrolled" action for every bill — many
    states jump straight from the second-chamber "Passed" action to a "Signed
    by Governor" action with nothing in between. For any bill that ended up
    signed/enacted, we synthesize an "Awaiting Governor" card at the LAST
    passed_chamber date so the timeline shows intro → awaiting gov → became
    law as three cards instead of two.
    """
    cards_raw: list[EventCard] = []
    bills_by_id = {r["bill_id"]: r for _, r in bills.iterrows()}

    # Pre-compute, per bill: latest passed_chamber date + whether a
    # signed/enacted event exists. Used below to synthesize "Awaiting Gov".
    last_passed_chamber: dict[str, pd.Timestamp] = {}
    has_became_law: set = set()
    if events is not None and not events.empty:
        for _, e in events.iterrows():
            bid = e["bill_id"]
            if bid not in bills_by_id:
                continue
            etype = e.get("event_type") or ""
            d = pd.to_datetime(e.get("date"), errors="coerce")
            if pd.isna(d):
                continue
            if etype == "passed_chamber":
                cur = last_passed_chamber.get(bid)
                if cur is None or d > cur:
                    last_passed_chamber[bid] = d
            elif etype in ("signed", "enacted"):
                has_became_law.add(bid)

    if events is not None and not events.empty:
        for _, e in events.iterrows():
            bid = e["bill_id"]
            if bid not in bills_by_id:
                continue
            etype = e.get("event_type") or ""
            group = STATUS_GROUP.get(etype, None)
            if group is None:
                continue
            # LegiScan logs "Signed by the Speaker" and "Signed by the President"
            # as chamber-transmittal actions — they are NOT the governor signing
            # the bill into law. Drop signed events that lack "Governor" in the
            # raw action text so a vetoed bill doesn't sprout a phantom
            # "Became law" card between its passage and its veto.
            if etype in ("signed", "enacted"):
                action = str(e.get("action_text") or "").lower()
                if action and "governor" not in action and "chaptered" not in action and "effective" not in action:
                    continue
            # LegiScan logs intermediate failures ("Amendment(s) Failed",
            # "Indefinitely Postponed in committee") with event_type=failed
            # even when the bill ultimately becomes law. Suppress these
            # killed-stage events on bills that became law or made it through
            # both chambers — the bill itself isn't dead.
            if group == "killed":
                bill_row = bills_by_id.get(bid)
                cur_status = (bill_row.get("current_status") if bill_row is not None else "") or ""
                if cur_status in ("enacted", "passed", "passed_chamber") or bid in has_became_law:
                    continue
            d = pd.to_datetime(e.get("date"), errors="coerce")
            if pd.isna(d):
                continue
            cards_raw.append(EventCard(
                bill_id=bid,
                event_date=d,
                stage_group=group,
                raw_event_type=etype,
            ))

    # Synthesize an "Awaiting Governor" (passed) card for every bill that
    # cleared both chambers — whether it went on to be signed OR is currently
    # sitting on the governor's desk. LegiScan does NOT emit an "Enrolled"
    # action for most states, so we detect the moment by:
    #   1. current_status == "passed" (enrolled, awaiting gov), OR
    #   2. current_status == "enacted" OR there's a signed/enacted event
    # In both cases the last `passed_chamber` event is the moment the bill
    # actually cleared the legislature.
    for bid, last_pc in last_passed_chamber.items():
        bill_row = bills_by_id.get(bid)
        cur_status = (bill_row.get("current_status") if bill_row is not None else "") or ""
        # Vetoed bills DID pass both chambers and sit on the governor's desk,
        # so they legitimately had an Awaiting-Gov stage. Show it.
        cleared_chambers = (
            cur_status in ("passed", "enacted", "vetoed") or bid in has_became_law
        )
        if not cleared_chambers:
            continue
        already_has_passed = any(
            c.bill_id == bid and c.stage_group == "passed" for c in cards_raw
        )
        if already_has_passed:
            continue
        cards_raw.append(EventCard(
            bill_id=bid,
            event_date=last_pc,
            stage_group="passed",
            raw_event_type="passed",
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


def render_timeline(bills: pd.DataFrame, events: pd.DataFrame | None = None,
                    zoom: float = 1.0):
    """Emit the complete timeline DOM at the given zoom factor. Zoom is a pure
    horizontal multiplier on canvas width (and therefore on every element's x);
    vertical layout and row-packing are unaffected."""
    if bills is None or bills.empty:
        return (
            [html.Div("No bills match the current filters.",
                      style={"position": "absolute", "top": "48%", "left": "50%",
                              "transform": "translate(-50%, -50%)", "color": GRAY_500})],
            "0 bills",
            CANVAS_HEIGHT,
        )

    cards = _collect_events(bills, events if events is not None else pd.DataFrame())
    if not cards:
        return [], "0 stage events", CANVAS_HEIGHT

    if len(cards) > MAX_CARDS:
        n_bills = len({c.bill_id for c in cards})
        msg = (f"{len(cards):,} stage events across {n_bills:,} bills exceeds the "
               f"{MAX_CARDS:,}-card render cap. Narrow the state, session, status, "
               f"or impact-score filters to show fewer bills.")
        return (
            [html.Div(msg,
                      style={"position": "absolute", "top": "48%", "left": "50%",
                              "transform": "translate(-50%, -50%)", "color": GRAY_500,
                              "maxWidth": "560px", "textAlign": "center",
                              "lineHeight": "1.4"})],
            f"{len(cards):,} stage events · render cap is {MAX_CARDS:,} — narrow filters to display",
            CANVAS_HEIGHT,
        )

    d_min = min(c.event_date for c in cards) - pd.Timedelta(days=5)
    d_max = max(c.event_date for c in cards) + pd.Timedelta(days=5)
    total_days = max(1, (d_max - d_min).days)

    canvas_w = _canvas_width_for([c.event_date for c in cards], d_min, d_max, zoom=zoom)
    usable_w = canvas_w - 2 * MARGIN_X

    for c in cards:
        frac = (c.event_date - d_min).days / total_days
        c.x_px = MARGIN_X + int(frac * usable_w)

    cards, dropped, row_defs = _pack_rows(cards)

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
    ]

    # Session bands — one translucent rect + label per legislative session
    # intersecting the visible window. Generalized across states: the start /
    # end dates come from bill_events aggregation in loaders.sessions_in_range,
    # so this renders correctly for every state we pull.
    try:
        from loaders.bills import sessions_in_range
        states_in_view = sorted(bills["state"].dropna().unique().tolist()) if "state" in bills.columns else []
        sessions = sessions_in_range(states_in_view, d_min, d_max)
    except Exception:
        sessions = pd.DataFrame()
    if sessions is not None and not sessions.empty:
        for _, srow in sessions.iterrows():
            actual_start = pd.to_datetime(srow["start_date"])
            actual_end = pd.to_datetime(srow["end_date"])
            s_start = max(actual_start, d_min)
            s_end   = min(actual_end, d_max)
            if s_end <= s_start:
                continue
            left_frac = (s_start - d_min).days / total_days
            right_frac = (s_end - d_min).days / total_days
            x0 = MARGIN_X + int(left_frac * usable_w)
            x1 = MARGIN_X + int(right_frac * usable_w)
            width = max(1, x1 - x0)
            children.append(html.Div(
                className="session-band",
                style={"left": f"{x0}px", "width": f"{width}px"},
            ))
            children.append(html.Div(
                srow['session_name'],
                className="session-band-label",
                style={"left": f"{x0 + 6}px"},
                title=srow['session_name'],
            ))
            sname = srow['session_name']
            children.append(html.Div(
                f"{sname} Start: {actual_start.strftime('%b %d, %Y')}",
                className="session-date-label session-date-start",
                style={"left": f"{x0}px"},
            ))
            children.append(html.Div(
                f"{sname} End: {actual_end.strftime('%b %d, %Y')}",
                className="session-date-label session-date-end",
                style={"left": f"{x1}px"},
            ))

    children.append(html.Div(className="timeline-axis",
                              style={"left": f"{MARGIN_X}px", "right": f"{MARGIN_X}px"}))

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
        row_top, anchor = row_defs[c.row]

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
    max_row_top = max((t for t, _ in row_defs), default=0)
    canvas_h = max(CANVAS_HEIGHT, max_row_top + CARD_H + 40)
    return children, meta, canvas_h


def canvas_bounds(bills: pd.DataFrame, events: pd.DataFrame | None = None):
    """Return (d_min_iso, d_max_iso) of the event span, or None if empty.
    Used by the clientside drag-zoom handler to translate pixel coords to dates."""
    if bills is None or bills.empty:
        return None
    cards = _collect_events(bills, events if events is not None else pd.DataFrame())
    if not cards:
        return None
    d_min = min(c.event_date for c in cards) - pd.Timedelta(days=5)
    d_max = max(c.event_date for c in cards) + pd.Timedelta(days=5)
    return d_min.strftime("%Y-%m-%d"), d_max.strftime("%Y-%m-%d")


def canvas_style_for(bills: pd.DataFrame, events: pd.DataFrame | None = None,
                     zoom: float = 1.0) -> dict:
    """Canvas width = density-fit * zoom. Height = CANVAS_HEIGHT."""
    if bills is None or bills.empty:
        return {"minWidth": f"{MIN_CANVAS_WIDTH}px", "height": f"{CANVAS_HEIGHT}px"}
    cards = _collect_events(bills, events if events is not None else pd.DataFrame())
    if not cards:
        return {"minWidth": f"{MIN_CANVAS_WIDTH}px", "height": f"{CANVAS_HEIGHT}px"}
    d_min = min(c.event_date for c in cards) - pd.Timedelta(days=5)
    d_max = max(c.event_date for c in cards) + pd.Timedelta(days=5)
    w = _canvas_width_for([c.event_date for c in cards], d_min, d_max, zoom=zoom)
    return {"width": f"{w}px", "height": f"{CANVAS_HEIGHT}px"}
