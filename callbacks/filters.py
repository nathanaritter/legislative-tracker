"""
Filter cascade: state → counties → cities, plus aggregation into filters-store.
"""

from dash import Input, Output, State, callback, ctx, ALL, no_update
from datetime import date, timedelta

from loaders.bills import geography_options


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
    Input("risk-filter", "value"),
    Input("date-filter-start", "date"),
    Input("date-filter-end", "date"),
)
def collect_filters(state, counties, cities, statuses, subjects, risk, start, end):
    return {
        "states": [state] if state else [],
        "counties": counties or [],
        "cities": cities or [],
        "statuses": statuses or [],
        "subjects": subjects or [],
        "risk": risk or [0, 100],
        "start": start,
        "end": end,
    }


@callback(
    Output("state-filter", "value"),
    Output("status-filter", "value"),
    Output("subject-filter", "value"),
    Output("risk-filter", "value"),
    Output("date-filter-start", "date"),
    Output("date-filter-end", "date"),
    Input("reset-filters-btn", "n_clicks"),
    prevent_initial_call=True,
)
def reset_filters(_n):
    today = date.today()
    return None, [], [], [0, 100], today - timedelta(days=365 * 3), today
