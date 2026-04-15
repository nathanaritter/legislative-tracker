"""
Canonical dataframe schemas for bills and bill_events, plus helpers used by both
LegiScan and LegiStar connectors to normalize their outputs before writing CSVs.
"""

from __future__ import annotations

import pandas as pd


BILLS_COLUMNS = [
    "bill_id",                   # e.g. legiscan:CO:SB24-001 or legistar:denver:22-1524
    "source",                    # legiscan | legistar
    "state",                     # 2-letter state code
    "area_id",                   # joins to etl-base/processed/geography/areas.csv
    "jurisdiction_level",        # state | county | city
    "jurisdiction_name",
    "bill_number",
    "session",
    "title",
    "introduced_date",           # YYYY-MM-DD
    "last_action_date",          # YYYY-MM-DD
    "current_status",
    "sponsors_json",
    "subjects_json",
    "url",
    "text_blob_path",            # azure blob path to the stored PDF (empty until fetched)
    "cre_relevant",              # bool
    "cre_keywords_hit",          # ';'-delimited string
    "ai_summary",                # populated by the AI batch
    "ai_risk_score",             # 0-100, populated by AI batch
    "ai_risk_breakdown_json",
    "ai_model_version",
    "last_updated",              # ISO8601
]

# Long-format event log (fits etl-base/etl/shared/schema.py standard schema).
BILL_EVENTS_COLUMNS = [
    "area_id", "date", "metric", "bill_id", "event_type", "chamber", "value",
]


def empty_bills_df() -> pd.DataFrame:
    return pd.DataFrame(columns=BILLS_COLUMNS)


def empty_events_df() -> pd.DataFrame:
    return pd.DataFrame(columns=BILL_EVENTS_COLUMNS)


def event_row(area_id, date, bill_id, event_type, chamber=None):
    return {
        "area_id": int(area_id) if area_id is not None else 0,
        "date": pd.to_datetime(date).strftime("%Y-%m-%d") if date else None,
        "metric": "bill_event",
        "bill_id": bill_id,
        "event_type": event_type,
        "chamber": chamber,
        "value": 1,
    }
