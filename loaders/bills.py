"""
Load bills, bill events, and geographic lookup data.

Reads parquet from local ../etl-base/parquet/... (USE_AZURE=false) or az:// blob (USE_AZURE=true).
If the parquet files don't exist yet (before the first ETL run), returns in-memory sample data so
the Dash app is still runnable for UI development.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from datetime import datetime, timedelta

import pandas as pd

from config import (
    USE_AZURE, AZURE_STORAGE_OPTIONS,
    BILLS_PARQUET, BILL_EVENTS_PARQUET, AREAS_PATH,
    TARGET_STATES,
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


# ----------------------------------------------------------------------------
# Sample fallback data — lets the UI render before the first ETL run.
# Real data takes over the moment bills.parquet exists.
# ----------------------------------------------------------------------------

def _sample_bills() -> pd.DataFrame:
    today = datetime.today().date()
    samples = [
        ("legiscan:CO:SB24-001", "legiscan", "CO", 8, "state", "Colorado State",
         "SB24-001", "2024", "Rent Control Local Authority",
         today - timedelta(days=120), today - timedelta(days=15), "passed_chamber",
         '[{"name":"Julie Gonzales","party":"D","role":"Senator","district":"34"}]',
         '["rent_control","tenant"]', "https://legiscan.com/CO/bill/SB24-001",
         "legislation/text/legiscan:CO:SB24-001.pdf",
         True, "rent control; tenant",
         "Authorizes local jurisdictions in Colorado to enact rent stabilization ordinances. "
         "Overrides a prior state pre-emption. Effective 2026-01-01 if signed.",
         72, '{"operational_impact":22,"capital_cost_impact":18,"passage_probability":15,"scope_breadth":12,"urgency":5}',
         "claude-opus-4-6"),
        ("legiscan:TX:HB2127", "legiscan", "TX", 48, "state", "Texas State",
         "HB2127", "2024", "Regulatory Consistency Act",
         today - timedelta(days=200), today - timedelta(days=60), "enacted",
         '[{"name":"Dustin Burrows","party":"R","role":"Representative","district":"83"}]',
         '["zoning","land_use","permitting"]', "https://legiscan.com/TX/bill/HB2127",
         "legislation/text/legiscan:TX:HB2127.pdf",
         True, "zoning; land use; permitting",
         "Pre-empts local ordinances that exceed state standards in nine fields including "
         "property regulation, labor, and natural resources.",
         58, '{"operational_impact":18,"capital_cost_impact":12,"passage_probability":18,"scope_breadth":8,"urgency":2}',
         "claude-opus-4-6"),
        ("legistar:denver:22-1524", "legistar", "CO", 8, "city", "Denver",
         "22-1524", "2024", "Short-Term Rental Enforcement",
         today - timedelta(days=90), today - timedelta(days=5), "passed",
         '[{"name":"Candi CdeBaca","party":"D","role":"Council","district":"9"}]',
         '["short_term_rental"]', "https://denver.legistar.com/LegislationDetail.aspx?ID=22-1524",
         "legislation/text/legistar:denver:22-1524.pdf",
         True, "short-term rental; STR",
         "Increases fines for unlicensed STRs and requires quarterly audits of listing platforms.",
         44, '{"operational_impact":14,"capital_cost_impact":8,"passage_probability":16,"scope_breadth":4,"urgency":2}',
         "claude-opus-4-6"),
    ]
    cols = [
        "bill_id", "source", "state", "area_id", "jurisdiction_level", "jurisdiction_name",
        "bill_number", "session", "title", "introduced_date", "last_action_date", "current_status",
        "sponsors_json", "subjects_json", "url", "text_blob_path",
        "cre_relevant", "cre_keywords_hit",
        "ai_summary", "ai_risk_score", "ai_risk_breakdown_json", "ai_model_version",
    ]
    df = pd.DataFrame(samples, columns=cols)
    df["introduced_date"] = pd.to_datetime(df["introduced_date"])
    df["last_action_date"] = pd.to_datetime(df["last_action_date"])
    return df


def _sample_events() -> pd.DataFrame:
    today = datetime.today().date()
    rows = [
        ("legiscan:CO:SB24-001", today - timedelta(days=120), "introduced", "senate"),
        ("legiscan:CO:SB24-001", today - timedelta(days=80),  "committee",  "senate"),
        ("legiscan:CO:SB24-001", today - timedelta(days=30),  "passed_chamber", "senate"),
        ("legiscan:TX:HB2127", today - timedelta(days=200), "introduced", "house"),
        ("legiscan:TX:HB2127", today - timedelta(days=150), "passed_chamber", "house"),
        ("legiscan:TX:HB2127", today - timedelta(days=100), "passed", "senate"),
        ("legiscan:TX:HB2127", today - timedelta(days=60),  "signed",   None),
        ("legiscan:TX:HB2127", today - timedelta(days=58),  "enacted",  None),
        ("legistar:denver:22-1524", today - timedelta(days=90), "introduced", "council"),
        ("legistar:denver:22-1524", today - timedelta(days=40), "committee",  "council"),
        ("legistar:denver:22-1524", today - timedelta(days=5),  "passed",     "council"),
    ]
    df = pd.DataFrame(rows, columns=["bill_id", "date", "event_type", "chamber"])
    df["date"] = pd.to_datetime(df["date"])
    return df


@lru_cache(maxsize=1)
def load_bills() -> pd.DataFrame:
    df = _read_parquet(BILLS_PARQUET)
    if df is None or df.empty:
        logger.info("bills.parquet not found — using sample data")
        return _sample_bills()
    df["introduced_date"] = pd.to_datetime(df.get("introduced_date"), errors="coerce")
    df["last_action_date"] = pd.to_datetime(df.get("last_action_date"), errors="coerce")
    return df


@lru_cache(maxsize=1)
def load_events() -> pd.DataFrame:
    df = _read_parquet(BILL_EVENTS_PARQUET)
    if df is None or df.empty:
        logger.info("bill_events.parquet not found — using sample data")
        return _sample_events()
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
    bills = load_bills().copy()

    states = filters.get("states") or []
    if states:
        bills = bills[bills["state"].isin(states)]

    statuses = filters.get("statuses") or []
    if statuses:
        bills = bills[bills["current_status"].isin(statuses)]

    subjects = filters.get("subjects") or []
    if subjects:
        def has_subject(js):
            try:
                tags = json.loads(js) if isinstance(js, str) else (js or [])
            except Exception:
                return False
            return any(s in tags for s in subjects)
        bills = bills[bills["subjects_json"].apply(has_subject)]

    risk = filters.get("risk") or [0, 100]
    if "ai_risk_score" in bills.columns:
        mask = bills["ai_risk_score"].fillna(0).between(risk[0], risk[1])
        bills = bills[mask]

    cre_only = filters.get("cre_only", True)
    if cre_only and "cre_relevant" in bills.columns:
        # AI sets cre_relevant to True/False; before enrichment it's None (unknown) —
        # keep unknowns visible so freshly-fetched bills are discoverable before AI runs.
        bills = bills[bills["cre_relevant"].fillna(True).astype(bool)]

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
