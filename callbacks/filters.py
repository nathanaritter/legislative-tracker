"""
Filter cascade: state → counties → cities, plus aggregation into filters-store.
"""

from dash import Input, Output, State, callback, ctx, no_update
from datetime import date, timedelta

from loaders.bills import geography_options


@callback(
    Output("county-filter", "options"),
    Output("county-filter", "value"),
    Input("state-filter", "value"),
    State("county-filter", "value"),
    prevent_initial_call=False,
)
def update_counties(states, current):
    county_opts, _ = geography_options(states or [], [])
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
def update_cities(states, counties, current):
    _, city_opts = geography_options(states or [], counties or [])
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
    Input("date-filter", "start_date"),
    Input("date-filter", "end_date"),
    Input("cre-only-filter", "value"),
)
def collect_filters(states, counties, cities, statuses, subjects, risk, start, end, cre_only):
    return {
        "states": states or [],
        "counties": counties or [],
        "cities": cities or [],
        "statuses": statuses or [],
        "subjects": subjects or [],
        "risk": risk or [0, 100],
        "start": start,
        "end": end,
        "cre_only": "on" in (cre_only or []),
    }


@callback(
    Output("state-filter", "value"),
    Output("status-filter", "value"),
    Output("subject-filter", "value"),
    Output("risk-filter", "value"),
    Output("date-filter", "start_date"),
    Output("date-filter", "end_date"),
    Output("cre-only-filter", "value"),
    Input("reset-filters-btn", "n_clicks"),
    prevent_initial_call=True,
)
def reset_filters(_n):
    today = date.today()
    return [], [], [], [0, 100], today - timedelta(days=365), today, ["on"]
