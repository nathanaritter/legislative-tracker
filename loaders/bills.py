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


# ----------------------------------------------------------------------------
# Sample fallback data — lets the UI render before the first ETL run.
# Real data takes over the moment bills.parquet exists.
# ----------------------------------------------------------------------------

def _sample_bills() -> pd.DataFrame:
    """DEMO-ONLY placeholder data. Bill numbers all start with DEMO- so they
    can't be mistaken for real legislation. Replaced the moment a real
    bills.parquet exists under ../etl-base/parquet/market/legislation/.
    """
    today = datetime.today().date()

    def _breakdown(score: int) -> str:
        # Distribute the composite score across the 5 components proportionally
        # to their max weights so demo bars look realistic but varied.
        maxes = {"operational_impact": 30, "capital_cost_impact": 25,
                 "passage_probability": 20, "scope_breadth": 15, "urgency": 10}
        total_max = sum(maxes.values())
        factor = score / 100.0
        out = {}
        for k, m in maxes.items():
            # Small deterministic jitter per key so components differ.
            jitter = ((hash(k) % 7) - 3) / 10.0
            out[k] = max(0, min(m, round(m * factor + jitter)))
        return json.dumps(out)

    def _rationale(score: int) -> str:
        severity = "low" if score < 40 else ("moderate" if score < 70 else "high")
        return json.dumps({
            "operational_impact": f"Demo rationale: {severity} operational impact assessed from the bill summary.",
            "capital_cost_impact": f"Demo rationale: {severity} projected capex and fees exposure.",
            "passage_probability": "Demo rationale: derived from current status, sponsor count, and chamber math.",
            "scope_breadth": "Demo rationale: jurisdiction population × asset classes touched.",
            "urgency": "Demo rationale: estimated effective date proximity.",
        })

    sponsors_demo = '[{"name":"Demo Sponsor A","party":"D","role":"Senator","district":"—"},' \
                    '{"name":"Demo Sponsor B","party":"R","role":"Representative","district":"—"}]'

    def mk(bill_id, state, area_id, level, juris, number, title, intro, last, status,
           subjects, score, direction):
        # direction: "favorable" | "adverse" | "mixed" — how the bill nets out for CRE.
        return (
            bill_id, "demo", state, area_id, level, juris,
            number, "Demo session", title,
            intro, last, status,
            sponsors_demo, subjects, "", "",
            True, "",
            "Demo placeholder. Real bill summaries and risk rationales appear after LegiScan + the AI batch run.",
            score, _breakdown(score), "demo", _rationale(score),
            direction,
        )

    samples = [
        # State-level DEMO bills, spread across target markets + statuses. Direction
        # varies: pre-emption + zoning liberalization bills are favorable for CRE
        # owners; rent control / surveillance pricing bans / eviction expansions
        # are adverse; property-tax transparency / insurance reform are mixed.
        mk("demo:CO:DEMO-01", "CO", 8,  "state", "Colorado State", "DEMO-01", "Local Rent Stabilization Authority", today - timedelta(days=120), today - timedelta(days=15),  "passed_chamber", '["rent_control"]',      72, "adverse"),
        mk("demo:CO:DEMO-02", "CO", 8,  "state", "Colorado State", "DEMO-02", "Utility Billing Transparency",        today - timedelta(days=60),  today - timedelta(days=20),  "in_committee",   '["habitability"]',      55, "adverse"),
        mk("demo:CO:DEMO-03", "CO", 8,  "state", "Colorado State", "DEMO-03", "Uniform Property-Tax Protest Rules",  today - timedelta(days=150), today - timedelta(days=30),  "passed",         '["property_tax"]',      48, "favorable"),
        mk("demo:CO:DEMO-04", "CO", 8,  "state", "Colorado State", "DEMO-04", "Tenant-Lawyer Funding",               today - timedelta(days=70),  today - timedelta(days=25),  "in_committee",   '["eviction"]',          40, "adverse"),
        mk("demo:CO:DEMO-05", "CO", 8,  "state", "Colorado State", "DEMO-05", "Surveillance Pricing Ban",            today - timedelta(days=40),  today - timedelta(days=10),  "introduced",     '["rent_control"]',      68, "adverse"),
        mk("demo:TX:DEMO-06", "TX", 48, "state", "Texas State",    "DEMO-06", "Local Pre-emption Act (DEMO)",        today - timedelta(days=400), today - timedelta(days=260), "enacted",        '["zoning","land_use"]', 58, "favorable"),
        mk("demo:FL:DEMO-07", "FL", 12, "state", "Florida State",  "DEMO-07", "Residential Landlord Pre-emption",    today - timedelta(days=320), today - timedelta(days=220), "enacted",        '["rent_control"]',      60, "favorable"),
        mk("demo:FL:DEMO-08", "FL", 12, "state", "Florida State",  "DEMO-08", "Property Insurance Transparency",     today - timedelta(days=130), today - timedelta(days=40),  "passed_chamber", '["insurance"]',         50, "mixed"),
        mk("demo:AZ:DEMO-09", "AZ", 4,  "state", "Arizona State",  "DEMO-09", "Starter Home Zoning",                 today - timedelta(days=90),  today - timedelta(days=5),   "passed",         '["zoning","adu"]',      74, "favorable"),
        mk("demo:UT:DEMO-10", "UT", 49, "state", "Utah State",     "DEMO-10", "Housing Affordability Amendments",    today - timedelta(days=180), today - timedelta(days=95),  "enacted",        '["affordable_housing"]',65, "mixed"),
        # City-level DEMO bills
        mk("demo:denver:DEMO-11",    "CO", 8,  "city", "Denver",             "Denver DEMO-11",    "Short-Term Rental Enforcement",   today - timedelta(days=220), today - timedelta(days=185), "passed",         '["short_term_rental"]', 44, "adverse"),
        mk("demo:austin:DEMO-12",    "TX", 48, "city", "Austin",             "Austin DEMO-12",    "Compatibility Standards Overhaul",today - timedelta(days=160), today - timedelta(days=45),  "passed_chamber", '["zoning"]',            52, "favorable"),
        mk("demo:nashville:DEMO-13", "TN", 47, "city", "Nashville-Davidson", "Nashville DEMO-13", "Workforce Housing Expansion",     today - timedelta(days=75),  today - timedelta(days=15),  "in_committee",   '["affordable_housing"]',40, "favorable"),
    ]
    cols = [
        "bill_id", "source", "state", "area_id", "jurisdiction_level", "jurisdiction_name",
        "bill_number", "session", "title", "introduced_date", "last_action_date", "current_status",
        "sponsors_json", "subjects_json", "url", "text_blob_path",
        "cre_relevant", "cre_keywords_hit",
        "ai_summary", "ai_risk_score", "ai_risk_breakdown_json", "ai_model_version",
        "ai_risk_rationale_json", "impact_direction",
    ]
    df = pd.DataFrame(samples, columns=cols)
    df["introduced_date"] = pd.to_datetime(df["introduced_date"])
    df["last_action_date"] = pd.to_datetime(df["last_action_date"])
    return df


def _sample_events() -> pd.DataFrame:
    """Synthetic per-stage events for the DEMO sample bills so progression bars
    inside each card have something to render. Stage coverage varies by bill so
    the UI exercises all states (introduced, committee, passed chamber, passed,
    signed, enacted, vetoed)."""
    today = datetime.today().date()
    t = today
    rows = [
        # DEMO-01 (passed_chamber)
        ("demo:CO:DEMO-01", t - timedelta(days=120), "introduced", "senate"),
        ("demo:CO:DEMO-01", t - timedelta(days=80),  "committee",  "senate"),
        ("demo:CO:DEMO-01", t - timedelta(days=15),  "passed_chamber", "senate"),
        # DEMO-02 (in_committee)
        ("demo:CO:DEMO-02", t - timedelta(days=60),  "introduced", "house"),
        ("demo:CO:DEMO-02", t - timedelta(days=20),  "committee",  "house"),
        # DEMO-03 (passed)
        ("demo:CO:DEMO-03", t - timedelta(days=150), "introduced", "senate"),
        ("demo:CO:DEMO-03", t - timedelta(days=95),  "passed_chamber", "senate"),
        ("demo:CO:DEMO-03", t - timedelta(days=30),  "passed", "house"),
        # DEMO-04 (in_committee)
        ("demo:CO:DEMO-04", t - timedelta(days=70),  "introduced", "house"),
        ("demo:CO:DEMO-04", t - timedelta(days=25),  "committee",  "house"),
        # DEMO-05 (introduced)
        ("demo:CO:DEMO-05", t - timedelta(days=10),  "introduced", "house"),
        # DEMO-06 (enacted)
        ("demo:TX:DEMO-06", t - timedelta(days=400), "introduced", "house"),
        ("demo:TX:DEMO-06", t - timedelta(days=320), "passed_chamber", "house"),
        ("demo:TX:DEMO-06", t - timedelta(days=280), "passed", "senate"),
        ("demo:TX:DEMO-06", t - timedelta(days=262), "signed", None),
        ("demo:TX:DEMO-06", t - timedelta(days=260), "enacted", None),
        # DEMO-07 (enacted)
        ("demo:FL:DEMO-07", t - timedelta(days=320), "introduced", "house"),
        ("demo:FL:DEMO-07", t - timedelta(days=260), "passed", "senate"),
        ("demo:FL:DEMO-07", t - timedelta(days=220), "enacted", None),
        # DEMO-08 (passed_chamber)
        ("demo:FL:DEMO-08", t - timedelta(days=130), "introduced", "senate"),
        ("demo:FL:DEMO-08", t - timedelta(days=40),  "passed_chamber", "senate"),
        # DEMO-09 (passed)
        ("demo:AZ:DEMO-09", t - timedelta(days=90),  "introduced", "house"),
        ("demo:AZ:DEMO-09", t - timedelta(days=30),  "passed_chamber", "house"),
        ("demo:AZ:DEMO-09", t - timedelta(days=5),   "passed", "senate"),
        # DEMO-10 (enacted)
        ("demo:UT:DEMO-10", t - timedelta(days=180), "introduced", "house"),
        ("demo:UT:DEMO-10", t - timedelta(days=130), "passed", "senate"),
        ("demo:UT:DEMO-10", t - timedelta(days=95),  "enacted", None),
        # Denver DEMO-11 (passed)
        ("demo:denver:DEMO-11", t - timedelta(days=220), "introduced", "council"),
        ("demo:denver:DEMO-11", t - timedelta(days=185), "passed", "council"),
        # Austin DEMO-12 (passed_chamber)
        ("demo:austin:DEMO-12", t - timedelta(days=160), "introduced", "council"),
        ("demo:austin:DEMO-12", t - timedelta(days=45),  "passed_chamber", "council"),
        # Nashville DEMO-13 (in_committee)
        ("demo:nashville:DEMO-13", t - timedelta(days=75), "introduced", "council"),
        ("demo:nashville:DEMO-13", t - timedelta(days=15), "committee",  "council"),
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
    from config import STATUS_GROUP

    bills = load_bills().copy()

    # Always enforce CRE-relevance — non-CRE bills are not surfaced in this app.
    # `cre_relevant` is True, False, or None (unknown; before AI run treat as kept).
    if "cre_relevant" in bills.columns:
        bills = bills[bills["cre_relevant"].fillna(True).astype(bool)]

    states = filters.get("states") or []
    if states:
        bills = bills[bills["state"].isin(states)]

    statuses = filters.get("statuses") or []
    if statuses:
        # Match the user's consolidated status bucket against each row's mapped group.
        bills = bills[bills["current_status"].map(STATUS_GROUP).isin(statuses)]

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
