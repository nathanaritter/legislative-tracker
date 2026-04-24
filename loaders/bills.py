"""
Load bills, bill events, and geographic lookup data.

Reads parquet from local ../etl-base/parquet/... (USE_AZURE=false) or az:// blob
(USE_AZURE=true). When parquet is absent, returns empty frames — the app renders
its "No bills." empty state rather than synthesizing fake rows.
"""

from __future__ import annotations

import logging
from functools import lru_cache

import pandas as pd

from config import (
    USE_AZURE, AZURE_STORAGE_OPTIONS,
    BILLS_PARQUET, BILL_EVENTS_PARQUET, AREAS_PATH,
    STATES,
)

logger = logging.getLogger(__name__)


def _read_parquet(path):
    """Read parquet from local path or az:// URI. Returns None if not found."""
    try:
        if USE_AZURE and str(path).startswith("az://"):
            return pd.read_parquet(path, storage_options=AZURE_STORAGE_OPTIONS)
        from pathlib import Path as _P
        if not _P(str(path)).exists():
            return None
        return pd.read_parquet(path)
    except FileNotFoundError:
        return None
    except Exception as exc:
        logger.warning("Failed to read parquet %s: %s", path, exc)
        return None


def _read_csv(path):
    try:
        if USE_AZURE and str(path).startswith("az://"):
            return pd.read_csv(path, storage_options=AZURE_STORAGE_OPTIONS)
        from pathlib import Path as _P
        if not _P(str(path)).exists():
            return None
        return pd.read_csv(path)
    except FileNotFoundError:
        return None
    except Exception as exc:
        logger.warning("Failed to read csv %s: %s", path, exc)
        return None



_EMPTY_BILLS_COLS = [
    "bill_id", "source", "state", "area_id", "jurisdiction_level", "jurisdiction_name",
    "bill_number", "session", "title", "introduced_date", "last_action_date", "current_status",
    "sponsors_json", "subjects_json", "url", "text_blob_path",
    "cre_relevant", "cre_keywords_hit",
    "ai_summary", "ai_risk_score", "ai_risk_breakdown_json",
    "ai_risk_rationale_json", "ai_direction_rationale", "impact_direction",
    "ai_categories", "ai_model_version", "ai_analyzed_date",
    "votes_json",
    "last_updated",
]


@lru_cache(maxsize=1)
def load_bills() -> pd.DataFrame:
    df = _read_parquet(BILLS_PARQUET)
    if df is None or df.empty:
        logger.info("bills.parquet not found — returning empty frame")
        return pd.DataFrame(columns=_EMPTY_BILLS_COLS)
    df["introduced_date"] = pd.to_datetime(df.get("introduced_date"), errors="coerce")
    df["last_action_date"] = pd.to_datetime(df.get("last_action_date"), errors="coerce")
    return df


@lru_cache(maxsize=1)
def load_events() -> pd.DataFrame:
    df = _read_parquet(BILL_EVENTS_PARQUET)
    if df is None or df.empty:
        logger.info("bill_events.parquet not found — returning empty frame")
        return pd.DataFrame(columns=["bill_id", "date", "event_type", "chamber"])
    df["date"] = pd.to_datetime(df.get("date"), errors="coerce")
    return df


@lru_cache(maxsize=1)
def load_areas() -> pd.DataFrame:
    df = _read_csv(AREAS_PATH)
    if df is None or df.empty:
        return pd.DataFrame(columns=["area_id", "area_name", "state_code", "geo_level"])
    return df


def geography_options(selected_states, selected_counties):
    """Return dicts of (county_opts, city_opts) keyed on `{area_id}|{level}` for cascading filters."""
    areas = load_areas()
    if areas.empty:
        return [], []

    if selected_states:
        areas = areas[areas["state_code"].isin(selected_states)] if "state_code" in areas.columns else areas

    counties = areas[areas.get("geo_level") == "COUNTY"] if "geo_level" in areas.columns else pd.DataFrame()
    cities = areas[areas.get("geo_level").isin(["PLACE", "CITY"])] if "geo_level" in areas.columns else pd.DataFrame()

    county_opts = [{"label": r.get("area_name", str(r["area_id"])), "value": int(r["area_id"])}
                   for _, r in counties.iterrows()]
    city_opts = [{"label": r.get("area_name", str(r["area_id"])), "value": int(r["area_id"])}
                 for _, r in cities.iterrows()]
    return county_opts, city_opts


def filter_bills(filters: dict) -> pd.DataFrame:
    from config import STATUS_GROUP

    bills = load_bills().copy()

    # Always enforce CRE-relevance — non-CRE bills are not surfaced in this app.
    # `cre_relevant` is True, False, or None (unknown; before AI run treat as kept).
    if "cre_relevant" in bills.columns:
        bills = bills[bills["cre_relevant"].fillna(False).astype(bool)]

    states = filters.get("states") or []
    if states:
        bills = bills[bills["state"].isin(states)]

    sessions = filters.get("sessions") or []
    if sessions and "session" in bills.columns:
        bills = bills[bills["session"].isin(sessions)]

    # Status filter is applied at event-level, not bill-level — see
    # callbacks/timeline.py render(). Bills stay in the frame as long as at
    # least one of their events matches the selected statuses; the timeline
    # then only emits cards for the matching stage-group events.

    # "Subjects" in the filter dict actually carries AI-category values (the
    # sidebar was renamed to "AI category" — key left as `subjects` for
    # backwards compat with existing store payloads).
    categories = filters.get("subjects") or []
    if categories and "ai_categories" in bills.columns:
        import json as _json
        def has_cat(js):
            try:
                tags = _json.loads(js) if isinstance(js, str) else (
                    js if isinstance(js, (list, tuple)) else []
                )
            except Exception:
                return False
            tags_norm = {str(t).strip() for t in (tags or [])}
            return any(c in tags_norm for c in categories)
        bills = bills[bills["ai_categories"].apply(has_cat)]

    # Total impact score range.
    risk = filters.get("risk") or [0, 100]
    if "ai_risk_score" in bills.columns and (risk[0] > 0 or risk[1] < 100):
        mask = bills["ai_risk_score"].fillna(0).between(risk[0], risk[1])
        bills = bills[mask]

    # Per-component ranges. Each slider filters on its component's value
    # from `ai_risk_breakdown_json`; they AND together. Rows without a
    # breakdown (un-enriched) are treated as 0 and only survive if the
    # slider's low bound is 0.
    component_ranges = filters.get("component_ranges") or {}
    if component_ranges and "ai_risk_breakdown_json" in bills.columns:
        import json as _json
        def _component_val(js, key):
            try:
                d = _json.loads(js) if isinstance(js, str) else (js or {})
                return int(d.get(key, 0) or 0)
            except Exception:
                return 0
        component_maxes = {
            "operational_impact": 30, "capital_cost_impact": 20,
            "pnl_impact": 25, "scope_breadth": 15, "enforcement_teeth": 10,
        }
        for comp, rng in component_ranges.items():
            lo, hi = rng[0], rng[1]
            # Skip component filters left at their default [0, max] — they
            # don't narrow anything and iterating would cost perf for nothing.
            if lo <= 0 and hi >= component_maxes.get(comp, 100):
                continue
            vals = bills["ai_risk_breakdown_json"].apply(
                lambda js, k=comp: _component_val(js, k)
            )
            bills = bills[vals.between(lo, hi)]

    start = pd.to_datetime(filters.get("start")) if filters.get("start") else None
    end = pd.to_datetime(filters.get("end")) if filters.get("end") else None
    if start is not None:
        bills = bills[bills["last_action_date"] >= start]
    if end is not None:
        bills = bills[bills["introduced_date"] <= end]

    return bills.reset_index(drop=True)


def get_bill(bill_id: str) -> dict | None:
    df = load_bills()
    row = df[df["bill_id"] == bill_id]
    if row.empty:
        return None
    return row.iloc[0].to_dict()


def get_events_for(bill_ids) -> pd.DataFrame:
    df = load_events()
    return df[df["bill_id"].isin(bill_ids)].copy()


@lru_cache(maxsize=1)
def load_sessions() -> pd.DataFrame:
    """Synthesize session bounds from bill introduction and last-action dates.

    Start = earliest introduced_date in the session.
    End   = latest last_action_date in the session (so every bill's final
            action — signing, veto, etc. — falls inside the band).

    Returns columns: state, session_name, start_date, end_date, bill_count.
    """
    bills = load_bills()
    if bills is None or bills.empty or "session" not in bills.columns:
        return pd.DataFrame(columns=["state", "session_name", "start_date",
                                      "end_date", "bill_count"])
    df = bills[["bill_id", "state", "session", "introduced_date", "last_action_date"]].copy()
    df["session_name"] = df["session"].fillna("").astype(str)
    df = df[df["session_name"] != ""]
    df["intro_ts"] = pd.to_datetime(df["introduced_date"], errors="coerce")
    df["last_ts"] = pd.to_datetime(df["last_action_date"], errors="coerce")
    df = df.dropna(subset=["intro_ts"])
    if df.empty:
        return pd.DataFrame(columns=["state", "session_name", "start_date",
                                      "end_date", "bill_count"])
    g = df.groupby(["state", "session_name"]).agg(
        start_date=("intro_ts", "min"),
        end_date=("last_ts", "max"),
        bill_count=("bill_id", "nunique"),
    ).reset_index()
    # Fill any null end_date (no last_action) with intro max + 30 days.
    mask = g["end_date"].isna()
    if mask.any():
        fallback = df.groupby(["state", "session_name"])["intro_ts"].max().reset_index()
        fallback.columns = ["state", "session_name", "fallback_end"]
        g = g.merge(fallback, on=["state", "session_name"], how="left")
        g.loc[mask, "end_date"] = g.loc[mask, "fallback_end"] + pd.Timedelta(days=30)
        g = g.drop(columns=["fallback_end"])
    return g.sort_values(["state", "start_date"]).reset_index(drop=True)


def sessions_in_range(states, d_min, d_max) -> pd.DataFrame:
    """Sessions intersecting the [d_min, d_max] window for the given state
    list. Returns a DataFrame filtered and sorted by start_date."""
    df = load_sessions()
    if df.empty:
        return df
    if states:
        df = df[df["state"].isin(states)]
    d_min = pd.to_datetime(d_min)
    d_max = pd.to_datetime(d_max)
    df = df[(df["end_date"] >= d_min) & (df["start_date"] <= d_max)]
    return df.sort_values("start_date").reset_index(drop=True)
