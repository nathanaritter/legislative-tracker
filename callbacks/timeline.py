"""
Render the card-based timeline + right-side bill legend.

Hide state is server-side. The store carries two sets:
    {"bills":  [bill_id, ...],            # fully-hidden bills
     "cards": ["bill_id|stage_group",...] # individually-hidden cards}

Legend swatch click  -> toggle bill full-hide.
Right-click on card  -> clientside menu -> toggle stage-hide or bill full-hide.
Reset view button    -> clear both sets AND reset zoom.
Reset filters button -> leaves hide state untouched.

The DOM is the filtered state — no clientside display mutation anywhere.
"""

import pandas as pd
from dash import Input, Output, State, callback, clientside_callback, ctx, ALL, html, no_update

from components.timeline import render_timeline, canvas_style_for
from loaders.bills import filter_bills, get_events_for
from config import STATUS_GROUP


_STATUS_COLOR = {
    "introduced": "#6A4C93",
    "passed":     "#1B5E83",
    "law":        "#2E7D32",
    "killed":     "#999999",
}

# Saturated red / green for the legend direction glyph. The previous desaturated
# "#059669" / "#dc2626" read as orangey-green and orange-red at 10px font size;
# these pop cleanly against the white sidebar.
_DIRECTION_GLYPH = {
    "favorable": ("▲", "#16a34a"),
    "adverse":   ("▼", "#ef4444"),
    "mixed":     ("◆", "#d97706"),
}


def _normalize_hidden(hidden):
    """Accepts the current store value in any of: None, legacy list, new dict.
    Returns (bills_list, cards_list, isolated_bill_or_None)."""
    if isinstance(hidden, dict):
        return (list(hidden.get("bills") or []),
                list(hidden.get("cards") or []),
                hidden.get("isolated") or None)
    if isinstance(hidden, list):
        return list(hidden), [], None
    return [], [], None


@callback(
    Output("timeline-canvas", "children"),
    Output("timeline-canvas", "style"),
    Output("timeline-meta", "children"),
    Output("bill-legend", "children"),
    Output("hidden-bills-store", "data"),
    Input("filters-store", "data"),
    Input("hidden-bills-store", "data"),
)
def render(filters, hidden):
    filters = filters or {}
    hidden_bills_list, hidden_cards_list, isolated_bill = _normalize_hidden(hidden)
    all_bills = filter_bills(filters)

    # Event-level filters: date range + status. Both applied at event level
    # so a bill's events outside the window / wrong status are excluded while
    # events inside the window / matching status survive.
    events = get_events_for(all_bills["bill_id"].tolist()) if not all_bills.empty else None

    start_ts = pd.to_datetime(filters.get("start"), errors="coerce") if filters.get("start") else None
    end_ts = pd.to_datetime(filters.get("end"), errors="coerce") if filters.get("end") else None
    if events is not None and not events.empty:
        if start_ts is not None:
            events = events[pd.to_datetime(events["date"], errors="coerce") >= start_ts]
        if end_ts is not None:
            events = events[pd.to_datetime(events["date"], errors="coerce") <= end_ts]
        events = events.reset_index(drop=True)

    # Strip chamber-transmittal "Signed" events BEFORE the status filter so
    # they don't pass the "law" bucket and pull in bills that are actually
    # still awaiting the governor. Same logic as in _collect_events —
    # only "Signed" events whose action_text mentions "governor" count as
    # became-law; everything else is a chamber transmittal (passed_chamber).
    if events is not None and not events.empty and "action_text" in events.columns:
        def _remap_signed(row):
            if row.get("event_type") not in ("signed", "enacted"):
                return row["event_type"]
            action = str(row.get("action_text") or "").lower()
            if not action or ("governor" not in action and "chaptered" not in action and "effective" not in action):
                return "passed_chamber"
            return row["event_type"]
        events = events.copy()
        events["event_type"] = events.apply(_remap_signed, axis=1)

    statuses = filters.get("statuses") or []
    if statuses and events is not None and not events.empty:
        kept = events["event_type"].map(STATUS_GROUP).isin(statuses)
        events = events[kept].reset_index(drop=True)

    # Bills with no surviving events in the window drop out entirely.
    if events is not None and not all_bills.empty:
        keep_bill_ids = set(events["bill_id"].tolist()) if not events.empty else set()
        all_bills = all_bills[all_bills["bill_id"].isin(keep_bill_ids)].reset_index(drop=True)

    # Clean stale hide entries that fell out of scope.
    scope_ids = set(all_bills["bill_id"].tolist()) if not all_bills.empty else set()
    cleaned_bills = sorted(b for b in hidden_bills_list if b in scope_ids)
    cleaned_cards = sorted(
        k for k in hidden_cards_list if k.split("|", 1)[0] in scope_ids
    )
    # Drop stale isolated pointer if its bill fell out of scope.
    if isolated_bill and isolated_bill not in scope_ids:
        isolated_bill = None
    hidden_bills_set = set(cleaned_bills)
    hidden_cards_set = set(cleaned_cards)

    # Timeline: when isolated is set, only that bill is visible (overrides
    # per-bill and per-stage hide sets). Otherwise drop fully-hidden bills +
    # events whose (bill_id, stage_group) is card-hidden.
    if isolated_bill and not all_bills.empty:
        visible_bills = all_bills[all_bills["bill_id"] == isolated_bill].reset_index(drop=True)
    else:
        visible_bills = (
            all_bills[~all_bills["bill_id"].isin(hidden_bills_set)].reset_index(drop=True)
            if not all_bills.empty else all_bills
        )
    if events is not None and not events.empty and not visible_bills.empty:
        mask = events["bill_id"].isin(set(visible_bills["bill_id"]))
        if hidden_cards_set:
            stage_key = events["bill_id"].astype(str) + "|" + \
                        events["event_type"].map(STATUS_GROUP).fillna("")
            mask = mask & ~stage_key.isin(hidden_cards_set)
        visible_events = events[mask].reset_index(drop=True)
    else:
        visible_events = events

    children, meta, canvas_h = render_timeline(visible_bills, visible_events)
    style = canvas_style_for(visible_bills, visible_events)
    style["height"] = f"{canvas_h}px"

    # Precompute how many stages each bill has (among current status-filter
    # scope) so we can distinguish "fully hidden" from "partially hidden".
    stage_count_by_bill = {}
    if events is not None and not events.empty:
        groups = (events.assign(_g=events["event_type"].map(STATUS_GROUP))
                        .dropna(subset=["_g"]))
        stage_count_by_bill = (groups.groupby("bill_id")["_g"].nunique().to_dict())

    hidden_stages_per_bill = {}
    for key in hidden_cards_set:
        b, _, _ = key.partition("|")
        hidden_stages_per_bill[b] = hidden_stages_per_bill.get(b, 0) + 1

    # Legend: sort by ai_risk_score DESC (worst first), nulls at bottom.
    legend_items = [html.H5("Bills in view")]
    if all_bills.empty:
        legend_items.append(html.Div("No bills.", style={"color": "#6b7280", "fontSize": "11px"}))
    else:
        sorted_bills = all_bills.copy()
        sorted_bills["_risk"] = sorted_bills.get("ai_risk_score")
        sorted_bills = sorted_bills.sort_values(
            "_risk", ascending=False, na_position="last"
        )
        for _, row in sorted_bills.iterrows():
            bill_id = row["bill_id"]
            fully_hidden = bill_id in hidden_bills_set
            n_stages = stage_count_by_bill.get(bill_id, 0)
            n_hidden_stages = hidden_stages_per_bill.get(bill_id, 0)
            # Fully hidden also covers the case where every stage is card-hidden.
            if not fully_hidden and n_stages and n_hidden_stages >= n_stages:
                fully_hidden = True
            partially_hidden = (not fully_hidden) and n_hidden_stages > 0

            group = STATUS_GROUP.get(row.get("current_status") or "introduced", "introduced")
            color = _STATUS_COLOR.get(group, "#6A4C93")
            label = f"{row.get('bill_number','')} — {row.get('title','')}"
            direction_raw = row.get("impact_direction")
            direction = str(direction_raw).lower() if direction_raw and not (isinstance(direction_raw, float) and pd.isna(direction_raw)) else ""
            dir_glyph, dir_color = _DIRECTION_GLYPH.get(direction, ("", None))
            glyph_el = (
                html.Span(dir_glyph, className="legend-dir",
                          style={"color": dir_color, "marginRight": "2px"},
                          title={"favorable": "Favorable for MF owners",
                                 "adverse": "Adverse for MF owners",
                                 "mixed": "Mixed impact for MF"}.get(direction, ""))
                if dir_glyph else None
            )
            label_children = [glyph_el, label] if glyph_el is not None else [label]

            # Visibility icon at the far right. The icon itself is static —
            # click handling is done by assets/card_menu.js, which opens the
            # shared "Bill actions" menu (Isolate / Hide whole bill / Show)
            # next to the icon. Icon glyph just reflects the bill's current
            # visibility state.
            is_isolated = (isolated_bill == bill_id)
            if isolated_bill and not is_isolated:
                vis_cls = "bi bi-eye-slash legend-hide-icon hidden-full"
                vis_title = "Another bill is isolated · click for options"
            elif is_isolated:
                vis_cls = "bi bi-bullseye legend-hide-icon isolated"
                vis_title = "Isolated · click for options"
            elif fully_hidden:
                vis_cls = "bi bi-eye-slash-fill legend-hide-icon hidden-full"
                vis_title = "Hidden · click for options"
            elif partially_hidden:
                vis_cls = "bi bi-eye legend-hide-icon hidden-partial"
                vis_title = f"{n_hidden_stages} of {n_stages} stages hidden · click for options"
            else:
                vis_cls = "bi bi-eye-fill legend-hide-icon"
                vis_title = "Click for options (isolate / hide)"
            status_icon = html.I(
                className=vis_cls,
                title=vis_title,
                **{"data-bill-id": bill_id,
                    "data-is-hidden": "1" if fully_hidden else "0",
                    "data-is-isolated": "1" if is_isolated else "0"},
            )

            score = row.get("ai_risk_score")
            risk_chip = None
            try:
                s = float(score) if score is not None else None
            except (TypeError, ValueError):
                s = None
            if s is not None:
                risk_chip = html.Span(f"{s:.0f}", className="legend-risk")

            row_children = [
                html.Span(
                    className="swatch",
                    style={"background": color},
                    id={"type": "bill-legend-swatch", "bill_id": bill_id},
                    n_clicks=0,
                    title="Click to hide / show bill",
                ),
                html.Span(
                    label_children,
                    className="label",
                    title=label,
                    id={"type": "bill-legend-label", "bill_id": bill_id},
                    n_clicks=0,
                ),
            ]
            if risk_chip is not None:
                row_children.append(risk_chip)
            row_children.append(status_icon)

            cls = "bill-legend-item"
            if is_isolated:
                cls += " isolated"
            elif isolated_bill:
                cls += " isolated-other"
            elif fully_hidden:
                cls += " hidden"
            elif partially_hidden:
                cls += " partial-hidden"
            legend_items.append(html.Div(
                row_children,
                className=cls,
                **{"data-bill-id": bill_id},
            ))

    new_store = {"bills": cleaned_bills, "cards": cleaned_cards, "isolated": isolated_bill}
    current_store = {"bills": sorted(hidden_bills_list), "cards": sorted(hidden_cards_list),
                      "isolated": (hidden or {}).get("isolated") if isinstance(hidden, dict) else None}
    hidden_out = new_store if new_store != current_store else no_update
    return children, style, meta, legend_items, hidden_out


# ----------------------------------------------------------------------------
# Swatch click -> toggle bill full-hide.
# ----------------------------------------------------------------------------
@callback(
    Output("hidden-bills-store", "data", allow_duplicate=True),
    Input({"type": "bill-legend-swatch", "bill_id": ALL}, "n_clicks"),
    State("hidden-bills-store", "data"),
    prevent_initial_call=True,
)
def toggle_bill_hidden(_n_clicks, hidden):
    trig = ctx.triggered_id
    if not trig or not isinstance(trig, dict) or trig.get("type") != "bill-legend-swatch":
        return no_update
    if not any(x for x in (_n_clicks or []) if x):
        return no_update
    bill_id = trig.get("bill_id")
    if not bill_id:
        return no_update
    bills_list, cards_list, isolated = _normalize_hidden(hidden)
    bills_set = set(bills_list)
    if bill_id in bills_set:
        bills_set.discard(bill_id)
    else:
        bills_set.add(bill_id)
        # When fully hiding a bill, clear any per-stage entries for it so the
        # legend icon flips cleanly back to "partial" on the next per-stage hide.
        cards_list = [k for k in cards_list if not k.startswith(bill_id + "|")]
        # Swatch-hiding a bill also clears isolate if the isolated bill is
        # the one being hidden (otherwise hide has no visible effect).
        if isolated == bill_id:
            isolated = None
    return {"bills": sorted(bills_set), "cards": sorted(cards_list), "isolated": isolated}


# Mirror the hidden-bills-store into a window global so the right-click menu
# JS (assets/card_menu.js) can read current state without calling private Dash
# APIs. Writes go through dash_clientside.set_props; this is read-through only.
clientside_callback(
    """
    function(data) {
        window.__hiddenStoreShadow = data || {bills: [], cards: []};
        return null;
    }
    """,
    Output("_shadow-sink", "data"),
    Input("hidden-bills-store", "data"),
)


# Zoom is pure clientside CSS transform (assets/timeline_zoom.js).
# No server-side zoom state anymore.
