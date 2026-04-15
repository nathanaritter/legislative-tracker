"""
Timeline card + Plotly horizontal Gantt figure builder.

Input is a DataFrame of bill events (one row per status transition per bill).
The figure draws one bar per event span, colored by event_type.
"""

import pandas as pd
import plotly.graph_objects as go
from dash import html, dcc

from config import EVENT_COLORS, GRAY_200, GRAY_500, GRAY_700


def build_timeline_card():
    return html.Div(
        [
            html.H5("Legislation timeline"),
            html.Div(id="timeline-meta", style={"fontSize": "12px", "color": GRAY_500, "marginBottom": "8px"}),
            dcc.Graph(
                id="timeline-figure",
                config={"displayModeBar": False},
                style={"height": "520px"},
            ),
        ],
        className="card",
    )


def empty_figure(message: str = "No bills match the current filters") -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(
        text=message, xref="paper", yref="paper", x=0.5, y=0.5,
        showarrow=False, font=dict(size=14, color=GRAY_500),
    )
    fig.update_layout(
        xaxis=dict(visible=False), yaxis=dict(visible=False),
        margin=dict(l=10, r=10, t=10, b=10), plot_bgcolor="#fff",
    )
    return fig


def build_timeline(bills: pd.DataFrame, events: pd.DataFrame, max_bills: int = 80) -> go.Figure:
    """
    bills: columns include bill_id, bill_number, title, state, ai_risk_score
    events: columns include bill_id, date, event_type
    """
    if bills is None or bills.empty or events is None or events.empty:
        return empty_figure()

    bills = bills.head(max_bills).copy()
    bills["label"] = bills.apply(
        lambda r: f"{r.get('state','')} {r.get('bill_number','')} — {str(r.get('title',''))[:60]}",
        axis=1,
    )

    events = events[events["bill_id"].isin(bills["bill_id"])].copy()
    events["date"] = pd.to_datetime(events["date"], errors="coerce")
    events = events.dropna(subset=["date"]).sort_values(["bill_id", "date"])

    # For each bill, compute event spans: a segment from event N to event N+1 (or to today for the latest).
    today = pd.Timestamp.today().normalize()
    segments = []
    for bill_id, grp in events.groupby("bill_id"):
        rows = grp.reset_index(drop=True)
        for i, row in rows.iterrows():
            start = row["date"]
            end = rows.loc[i + 1, "date"] if i + 1 < len(rows) else today
            if end <= start:
                end = start + pd.Timedelta(days=1)
            segments.append({
                "bill_id": bill_id,
                "start": start,
                "end": end,
                "event_type": row["event_type"],
            })

    seg_df = pd.DataFrame(segments)
    if seg_df.empty:
        return empty_figure()

    label_map = dict(zip(bills["bill_id"], bills["label"]))

    fig = go.Figure()
    drawn_legend = set()
    for etype, grp in seg_df.groupby("event_type"):
        color = EVENT_COLORS.get(etype, "#888888")
        show_legend = etype not in drawn_legend
        drawn_legend.add(etype)
        fig.add_trace(go.Bar(
            name=etype.replace("_", " ").title(),
            y=[label_map.get(bid, bid) for bid in grp["bill_id"]],
            x=(grp["end"] - grp["start"]).dt.total_seconds() * 1000,  # milliseconds width
            base=grp["start"],
            orientation="h",
            marker=dict(color=color, line=dict(width=0)),
            customdata=grp[["bill_id", "event_type"]].values,
            hovertemplate="<b>%{y}</b><br>%{customdata[1]}<br>%{base|%Y-%m-%d}<extra></extra>",
            showlegend=show_legend,
        ))

    fig.update_layout(
        barmode="stack",
        xaxis=dict(type="date", showgrid=True, gridcolor=GRAY_200),
        yaxis=dict(autorange="reversed", tickfont=dict(size=11, color=GRAY_700)),
        margin=dict(l=10, r=10, t=10, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(size=11)),
        plot_bgcolor="#fff",
        height=max(320, 22 * len(bills) + 80),
        bargap=0.25,
    )
    return fig
