"""
Filter cascade: state → counties → cities, plus aggregation into filters-store.
"""

from dash import Input, Output, State, callback, clientside_callback, ctx, ALL, no_update
from datetime import date, timedelta

from loaders.bills import geography_options


@callback(
    Output("date-filter-start", "value", allow_duplicate=True),
    Output("date-filter-end", "value", allow_duplicate=True),
    Input("state-filter", "value"),
    prevent_initial_call=True,
)
def update_date_range_for_state(state):
    """When the user switches states, auto-set the date range to cover
    the most recent legislative session so all bills in that session are
    visible and none appear outside a session band."""
    from loaders.bills import load_sessions
    import pandas as pd
    if not state:
        return no_update, no_update
    sessions = load_sessions()
    if sessions is None or sessions.empty:
        return no_update, no_update
    state_sessions = sessions[sessions["state"] == state].sort_values("start_date", ascending=False)
    if state_sessions.empty:
        return no_update, no_update
    # Use the most recent session's full span
    latest_session = state_sessions.iloc[0]
    start = pd.to_datetime(latest_session["start_date"]).strftime("%Y-%m-%d")
    end = pd.to_datetime(latest_session["end_date"]).strftime("%Y-%m-%d")
    return start, end


@callback(
    Output("county-filter", "options"),
    Output("county-filter", "value"),
    Input("state-filter", "value"),
    State("county-filter", "value"),
    prevent_initial_call=False,
)
def update_counties(state, current):
    states = [state] if state else []
    county_opts, _ = geography_options(states, [])
    valid_values = {o["value"] for o in county_opts}
    new_value = [v for v in (current or []) if v in valid_values]
    return county_opts, new_value


@callback(
    Output("session-filter", "options", allow_duplicate=True),
    Output("session-filter", "value", allow_duplicate=True),
    Input("state-filter", "value"),
    prevent_initial_call=True,
)
def update_sessions_for_state(state):
    from components.sidebar import _session_opts
    if not state:
        return [], []
    return _session_opts(state), []


@callback(
    Output("city-filter", "options"),
    Output("city-filter", "value"),
    Input("state-filter", "value"),
    Input("county-filter", "value"),
    State("city-filter", "value"),
    prevent_initial_call=False,
)
def update_cities(state, counties, current):
    states = [state] if state else []
    _, city_opts = geography_options(states, counties or [])
    valid_values = {o["value"] for o in city_opts}
    new_value = [v for v in (current or []) if v in valid_values]
    return city_opts, new_value


@callback(
    Output("filters-store", "data"),
    Input("state-filter", "value"),
    Input("county-filter", "value"),
    Input("city-filter", "value"),
    Input("status-filter", "value"),
    Input("subject-filter", "value"),
    Input("session-filter", "value"),
    Input("risk-filter", "value"),
    Input("risk-op-filter", "value"),
    Input("risk-capex-filter", "value"),
    Input("risk-pnl-filter", "value"),
    Input("risk-scope-filter", "value"),
    Input("risk-enforcement-filter", "value"),
    Input("date-filter-start", "value"),
    Input("date-filter-end", "value"),
)
def collect_filters(state, counties, cities, statuses, subjects, sessions,
                     risk, risk_op, risk_capex, risk_pnl, risk_scope,
                     risk_enforcement, start, end):
    # Session + date range are mutually exclusive: if any sessions are
    # selected, they take precedence and date range is ignored.
    if sessions:
        start = None
        end = None
    return {
        "states": [state] if state else [],
        "counties": counties or [],
        "cities": cities or [],
        "statuses": statuses or [],
        "subjects": subjects or [],
        "sessions": sessions or [],
        "risk": risk or [0, 100],
        "component_ranges": {
            "operational_impact":  risk_op or [0, 30],
            "capital_cost_impact": risk_capex or [0, 20],
            "pnl_impact":          risk_pnl or [0, 25],
            "scope_breadth":       risk_scope or [0, 15],
            "enforcement_teeth":   risk_enforcement or [0, 10],
        },
        "start": start,
        "end": end,
    }


@callback(
    Output("state-filter", "value"),
    Output("status-filter", "value"),
    Output("subject-filter", "value"),
    Output("session-filter", "value"),
    Output("risk-filter", "value"),
    Output("risk-op-filter", "value"),
    Output("risk-capex-filter", "value"),
    Output("risk-pnl-filter", "value"),
    Output("risk-scope-filter", "value"),
    Output("risk-enforcement-filter", "value"),
    Output("date-filter-start", "value"),
    Output("date-filter-end", "value"),
    Input("reset-filters-btn", "n_clicks"),
    prevent_initial_call=True,
)
def reset_filters(_n):
    # Sidebar reset. Does NOT touch hidden-bills-store — that's cleared by the
    # timeline's "Reset view" button in assets/card_menu.js instead. State is
    # required, so reset brings it back to CO (default) rather than clearing it.
    from components.sidebar import _default_date_range
    start, end = _default_date_range("CO")
    return ("CO", [], [], [], [0, 100],
            [0, 30], [0, 20], [0, 25], [0, 15], [0, 10],
            start.isoformat(), end.isoformat())


# Session + date range mutual-exclusive grey-out. When the user selects any
# sessions, the date range row dims + inputs disable. When sessions is empty,
# date range is active again.
clientside_callback(
    """
    function(sessions) {
        const hasSessions = Array.isArray(sessions) && sessions.length > 0;
        const row = document.getElementById('date-range-row');
        const heading = document.getElementById('date-range-heading');
        if (row) {
            row.style.opacity = hasSessions ? '0.4' : '1';
            row.style.pointerEvents = hasSessions ? 'none' : '';
        }
        if (heading) {
            heading.style.opacity = hasSessions ? '0.4' : '1';
        }
        document.querySelectorAll('#date-filter-start, #date-filter-end').forEach(el => {
            el.disabled = hasSessions;
        });
        return window.dash_clientside.no_update;
    }
    """,
    Output("date-range-row", "title"),   # throwaway sink
    Input("session-filter", "value"),
)
