"""
Sidebar filter stack. State is single-select (only one state at a time),
counties and cities are multi-select, 5 consolidated status buckets, risk
slider with live value readout, and a preset bar for the date range.
"""

from datetime import date, timedelta

from dash import html, dcc
import dash_bootstrap_components as dbc

from config import STATES, STATUS_GROUPS


def _opts(values):
    return [{"label": label, "value": code} for code, label in values]


def _session_opts(state=None):
    """Return session multi-select options from the sessions loader, filtered
    to the given state. Labels lead with the count of CRE-relevant bills so
    the user can see at a glance which sessions are worth opening, then the
    session name and date range."""
    try:
        from loaders.bills import load_sessions, load_bills
        import pandas as pd
        df = load_sessions()
        if df is None or df.empty:
            return []
        if state:
            df = df[df["state"] == state]
        df = df.sort_values("start_date", ascending=False)

        bills = load_bills()
        rel_counts = {}
        if bills is not None and not bills.empty and "session" in bills.columns:
            scope = bills[bills["state"] == state] if state else bills
            relevant = scope[scope["cre_relevant"] == True]  # noqa: E712
            rel_counts = relevant["session"].value_counts().to_dict()

        opts = []
        for _, r in df.iterrows():
            s = pd.to_datetime(r["start_date"])
            e = pd.to_datetime(r["end_date"])
            n_rel = int(rel_counts.get(r["session_name"], 0))
            label = (f"{n_rel} relevant · {r['session_name']} "
                     f"({s.strftime('%b %Y')} – {e.strftime('%b %Y')})")
            opts.append({"label": label, "value": r["session_name"]})
        return opts
    except Exception:
        return []


def _category_opts():
    """Dropdown options for the Category filter. Shows the human-readable
    label (Milestone taxonomy) while storing the snake_case category value
    for filtering. Only surfaces categories actually present in the loaded
    bills so users can't pick a tag that returns zero results."""
    from config import CATEGORY_LABEL
    try:
        import json
        from loaders.bills import load_bills
        df = load_bills()
        if df is None or df.empty or "ai_categories" not in df.columns:
            return []
        seen = set()
        for js in df["ai_categories"].dropna():
            try:
                tags = json.loads(js) if isinstance(js, str) else (
                    js if isinstance(js, (list, tuple)) else [js]
                )
            except Exception:
                tags = []
            for t in tags:
                t = str(t).strip()
                if t:
                    seen.add(t)
        return sorted(
            [{"label": CATEGORY_LABEL.get(s, s.replace("_", " ").title()),
              "value": s} for s in seen],
            key=lambda o: o["label"].lower(),
        )
    except Exception:
        return []


def _default_date_range(state="CO"):
    """Default to the most recent session for the default state so the user
    lands on a window that actually contains bills. Falls back to last 30 days
    only if no sessions exist for the state."""
    today = date.today()
    try:
        from loaders.bills import load_sessions
        import pandas as pd
        df = load_sessions()
        if df is None or df.empty:
            return today - timedelta(days=30), today
        df = df[df["state"] == state].sort_values("start_date", ascending=False)
        if df.empty:
            return today - timedelta(days=30), today
        latest = df.iloc[0]
        return (pd.to_datetime(latest["start_date"]).date(),
                pd.to_datetime(latest["end_date"]).date())
    except Exception:
        return today - timedelta(days=30), today


def build_sidebar():
    today = date.today()
    default_start, default_end = _default_date_range("CO")

    return html.Div(
        [
            html.H6("State"),
            dcc.Dropdown(
                id="state-filter",
                options=[{"label": s, "value": s} for s in STATES],
                value="CO", multi=False,
                clearable=False,
                placeholder="Select a state",
                className="dash-dropdown filter-row",
            ),

            html.H6("Counties"),
            dcc.Dropdown(
                id="county-filter",
                options=[], value=[], multi=True,
                placeholder="All counties",
                className="dash-dropdown filter-row",
            ),

            html.H6("Cities"),
            dcc.Dropdown(
                id="city-filter",
                options=[], value=[], multi=True,
                placeholder="All cities",
                className="dash-dropdown filter-row",
            ),

            html.H6("Status"),
            dcc.Dropdown(
                id="status-filter",
                options=_opts(STATUS_GROUPS),
                value=[], multi=True,
                placeholder="Any status",
                className="dash-dropdown filter-row",
            ),

            html.H6("Category"),
            dcc.Dropdown(
                id="subject-filter",
                options=_category_opts(),
                value=[], multi=True,
                placeholder="Any category",
                className="dash-dropdown filter-row",
            ),

            html.H6("Sessions"),
            dcc.Dropdown(
                id="session-filter",
                options=_session_opts("CO"),
                value=[], multi=True,
                placeholder="Any session",
                className="dash-dropdown filter-row",
                optionHeight=80,
            ),

            html.H6("Date range", id="date-range-heading"),
            html.Div(
                [
                    html.Div(
                        [
                            html.Div("Start", className="date-label"),
                            dcc.Input(
                                id="date-filter-start",
                                type="date",
                                value=default_start.isoformat(),
                                className="brand-dateinput",
                            ),
                        ]
                    ),
                    html.Div(
                        [
                            html.Div("End", className="date-label"),
                            dcc.Input(
                                id="date-filter-end",
                                type="date",
                                value=default_end.isoformat(),
                                className="brand-dateinput",
                            ),
                        ]
                    ),
                ],
                className="date-range-row",
                id="date-range-row",
            ),

            # Impact-score sliders live at the bottom of the filter stack —
            # they're the most nuanced knob and users typically set the other
            # filters first, then refine with these.
            html.H6("Impact score"),
            html.Div("Total (0–100)", className="slider-sublabel"),
            dcc.RangeSlider(
                id="risk-filter",
                min=0, max=100, step=1, value=[20, 100],
                marks=None, tooltip={"placement": "bottom", "always_visible": False},
                className="filter-row brand-slider",
            ),
            html.Div("Operational impact (0–30)", className="slider-sublabel"),
            dcc.RangeSlider(
                id="risk-op-filter",
                min=0, max=30, step=1, value=[0, 30],
                marks=None, tooltip={"placement": "bottom", "always_visible": False},
                className="filter-row brand-slider",
            ),
            html.Div("Capital cost impact (0–20)", className="slider-sublabel"),
            dcc.RangeSlider(
                id="risk-capex-filter",
                min=0, max=20, step=1, value=[0, 20],
                marks=None, tooltip={"placement": "bottom", "always_visible": False},
                className="filter-row brand-slider",
            ),
            html.Div("P&L impact (0–25)", className="slider-sublabel"),
            dcc.RangeSlider(
                id="risk-pnl-filter",
                min=0, max=25, step=1, value=[0, 25],
                marks=None, tooltip={"placement": "bottom", "always_visible": False},
                className="filter-row brand-slider",
            ),
            html.Div("Scope breadth (0–15)", className="slider-sublabel"),
            dcc.RangeSlider(
                id="risk-scope-filter",
                min=0, max=15, step=1, value=[0, 15],
                marks=None, tooltip={"placement": "bottom", "always_visible": False},
                className="filter-row brand-slider",
            ),
            html.Div("Enforcement teeth (0–10)", className="slider-sublabel"),
            dcc.RangeSlider(
                id="risk-enforcement-filter",
                min=0, max=10, step=1, value=[0, 10],
                marks=None, tooltip={"placement": "bottom", "always_visible": False},
                className="filter-row brand-slider",
            ),

            html.Hr(style={"margin": "14px 0 10px"}),
            dbc.Button(
                [html.I(className="bi bi-arrow-repeat", style={"marginRight": "6px"}), "Reset filters"],
                id="reset-filters-btn",
                color="secondary", outline=True, size="sm",
                style={"width": "100%"},
            ),
        ],
        className="app-sidebar",
    )
