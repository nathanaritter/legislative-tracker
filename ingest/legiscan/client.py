"""
LegiScan API client.

Flow:
    getSessionList(state)         -> session IDs for the state
    getMasterListRaw(session_id)  -> lightweight per-bill change_hash listing
    compare to blob-stored cursor -> only bills whose change_hash changed are fetched
    getBill(bill_id)              -> full bill detail; raw JSON written DIRECTLY TO BLOB
    getBillText(doc_id)           -> base64 PDF text; written DIRECTLY TO BLOB (cre-relevant only)

Nothing per-bill is ever written to the local filesystem. This is a hard constraint —
previous bulk runs caused millions of files on OneDrive.
"""

from __future__ import annotations

import base64
import json
import logging
import time
from datetime import datetime
from typing import Iterable, Iterator

import pandas as pd
import requests

from ingest.keyvault import get_secret
from ingest.schema import BILLS_COLUMNS, event_row
from ingest.legiscan.cre_filter import is_cre_relevant
from services.storage import get_client as get_storage


logger = logging.getLogger(__name__)
BASE_URL = "https://api.legiscan.com/"


# Map LegiScan event codes (from history list) to our event_type vocabulary.
# Codes: https://api.legiscan.com/docs/ (history action codes)
HISTORY_ACTION_MAP = {
    "Introduced": "introduced",
    "Prefiled": "introduced",
    "Referred": "in_committee",
    "Reported": "committee",
    "Passed": "passed_chamber",
    "Engrossed": "passed_chamber",
    "Enrolled": "passed",
    "Signed": "signed",
    "Chaptered": "enacted",
    "Effective": "enacted",
    "Vetoed": "vetoed",
    "Failed": "failed",
    "Died": "failed",
    "Amended": "amended",
    "Substituted": "amended",
}

STATUS_CODE_MAP = {
    1: "introduced",
    2: "in_committee",
    3: "passed_chamber",
    4: "passed",
    5: "vetoed",
    6: "enacted",
}


class LegiScanError(Exception):
    pass


class LegiScanClient:
    def __init__(self, api_key: str | None = None, timeout: int = 30):
        self.api_key = api_key or get_secret("LEGISCAN_API_KEY", "LEGISCAN-API-KEY")
        if not self.api_key:
            raise LegiScanError("LEGISCAN_API_KEY not set and not found in Key Vault")
        self.timeout = timeout
        self._session = requests.Session()

    def _call(self, op: str, **params) -> dict:
        qs = {"key": self.api_key, "op": op, **params}
        resp = self._session.get(BASE_URL, params=qs, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") != "OK":
            raise LegiScanError(f"LegiScan {op} failed: {data.get('alert', data)}")
        return data

    # ----- API wrappers ---------------------------------------------------

    def get_session_list(self, state: str) -> list[dict]:
        return self._call("getSessionList", state=state).get("sessions", [])

    def get_master_list_raw(self, session_id: int) -> dict[str, dict]:
        """Lightweight listing: {key: {bill_id, number, change_hash, url}, ...}"""
        data = self._call("getMasterListRaw", id=session_id).get("masterlist", {})
        # masterlist includes a 'session' key we don't want
        return {k: v for k, v in data.items() if isinstance(v, dict) and "bill_id" in v}

    def get_bill(self, bill_id: int) -> dict:
        return self._call("getBill", id=bill_id).get("bill", {})

    def get_bill_text(self, doc_id: int) -> dict:
        return self._call("getBillText", id=doc_id).get("text", {})


# ----------------------------------------------------------------------------
# Blob-backed cursor: remembers last-seen change_hash per bill so we fetch only
# changed bills on subsequent runs. Kept as a single JSON blob — not per-bill.
# ----------------------------------------------------------------------------

def _cursor_blob(state: str) -> str:
    return f"legislation/_state/legiscan_{state.lower()}_cursor.json"


def _load_cursor(state: str) -> dict:
    blob = get_storage().read_json(_cursor_blob(state))
    return blob or {}


def _save_cursor(state: str, cursor: dict) -> None:
    get_storage().write_json(_cursor_blob(state), cursor)


# ----------------------------------------------------------------------------
# Bill extraction — LegiScan JSON → our bills.csv / bill_events.csv rows.
# ----------------------------------------------------------------------------

def _extract_sponsors(bill: dict) -> list[dict]:
    out = []
    for s in bill.get("sponsors", []) or []:
        out.append({
            "name": s.get("name"),
            "party": s.get("party"),
            "role": s.get("role"),
            "district": s.get("district"),
            "sponsor_order": s.get("sponsor_order"),
        })
    return out


def _extract_subjects(bill: dict) -> list[str]:
    subs = []
    for s in bill.get("subjects", []) or []:
        name = s.get("subject_name") or s.get("subject") or ""
        if name:
            subs.append(str(name).lower().replace(" ", "_"))
    return subs


def _extract_history_events(bill: dict, bill_id: str, area_id: int) -> list[dict]:
    rows = []
    for h in bill.get("history", []) or []:
        action = h.get("action") or ""
        etype = None
        for key, mapped in HISTORY_ACTION_MAP.items():
            if key.lower() in action.lower():
                etype = mapped
                break
        if not etype:
            continue
        chamber = "senate" if h.get("chamber") == "S" else ("house" if h.get("chamber") == "H" else None)
        rows.append(event_row(area_id, h.get("date"), bill_id, etype, chamber))
    return rows


def _current_status(bill: dict) -> str:
    code = bill.get("status")
    try:
        code_int = int(code) if code is not None else None
    except (TypeError, ValueError):
        code_int = None
    return STATUS_CODE_MAP.get(code_int, "introduced")


def fetch_state_bills(
    state: str,
    area_id: int,
    session_ids: Iterable[int] | None = None,
    client: LegiScanClient | None = None,
    store_text: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Fetch all bills for the given state (and optional session subset).

    Returns (bills_df, events_df) — both following `ingest/schema.py` columns.
    Raw per-bill JSON is written to blob as a side effect; no local raw files are created.
    """
    client = client or LegiScanClient()
    cursor = _load_cursor(state)
    new_cursor = dict(cursor)

    sessions = client.get_session_list(state)
    if session_ids is not None:
        wanted = set(session_ids)
        sessions = [s for s in sessions if s.get("session_id") in wanted]

    bill_rows: list[dict] = []
    event_rows: list[dict] = []
    storage = get_storage()

    for sess in sessions:
        session_id = sess.get("session_id")
        session_name = sess.get("session_name") or str(sess.get("year_start"))
        try:
            master = client.get_master_list_raw(session_id)
        except LegiScanError as exc:
            logger.warning("Skipping session %s: %s", session_id, exc)
            continue

        for _, entry in master.items():
            bill_api_id = entry.get("bill_id")
            change_hash = entry.get("change_hash")
            if not bill_api_id or not change_hash:
                continue
            if cursor.get(str(bill_api_id)) == change_hash:
                continue  # unchanged since last run

            try:
                bill = client.get_bill(bill_api_id)
            except LegiScanError as exc:
                logger.warning("getBill failed for %s: %s", bill_api_id, exc)
                continue

            bill_number = bill.get("bill_number") or ""
            bill_id = f"legiscan:{state}:{bill_number}"

            # Write raw JSON to blob, NEVER to local disk.
            month = datetime.utcnow().strftime("%Y-%m")
            raw_blob = f"legislation/raw/legiscan/{state}/{month}/{bill_id.replace(':', '_')}.json.gz"
            try:
                storage.upload_json_gz(raw_blob, bill)
            except Exception as exc:
                logger.warning("Failed to write raw JSON for %s: %s", bill_id, exc)

            sponsors = _extract_sponsors(bill)
            subjects = _extract_subjects(bill)
            title = bill.get("title") or ""
            description = bill.get("description") or ""
            # Keyword hits are a *hint* only — CRE relevance is decided by the AI batch step.
            # No filter gate here; the 20x plan budget covers fetching everything.
            _, hits = is_cre_relevant(title, description, subjects)

            text_blob_path = ""
            if store_text:
                doc_id = None
                for t in bill.get("texts", []) or []:
                    if t.get("mime") in ("application/pdf", "text/html") and t.get("doc_id"):
                        doc_id = t["doc_id"]
                        break
                if doc_id:
                    try:
                        txt = client.get_bill_text(doc_id)
                        pdf_bytes = base64.b64decode(txt.get("doc", "")) if txt.get("doc") else b""
                        if pdf_bytes:
                            text_blob_path = f"legislation/text/{bill_id.replace(':', '_')}.pdf"
                            storage.upload_bytes(text_blob_path, pdf_bytes, content_type="application/pdf")
                    except Exception as exc:
                        logger.warning("getBillText failed for %s: %s", bill_id, exc)

            bill_rows.append({
                "bill_id": bill_id,
                "source": "legiscan",
                "state": state,
                "area_id": area_id,
                "jurisdiction_level": "state",
                "jurisdiction_name": f"{state} State",
                "bill_number": bill_number,
                "session": session_name,
                "title": title,
                "introduced_date": (bill.get("history", [{}])[0] or {}).get("date", ""),
                "last_action_date": bill.get("status_date", ""),
                "current_status": _current_status(bill),
                "sponsors_json": json.dumps(sponsors, separators=(",", ":")),
                "subjects_json": json.dumps(subjects, separators=(",", ":")),
                "url": bill.get("state_link") or bill.get("url") or "",
                "text_blob_path": text_blob_path,
                "cre_relevant": None,          # set by AI enrichment
                "cre_keywords_hit": ";".join(hits),
                "ai_summary": "",
                "ai_risk_score": None,
                "ai_risk_breakdown_json": "",
                "ai_model_version": "",
                "last_updated": datetime.utcnow().isoformat(timespec="seconds"),
            })

            event_rows.extend(_extract_history_events(bill, bill_id, area_id))
            new_cursor[str(bill_api_id)] = change_hash
            time.sleep(0.05)   # gentle pacing — LegiScan allows 30k/month, don't burn quota

    _save_cursor(state, new_cursor)

    bills_df = pd.DataFrame(bill_rows, columns=BILLS_COLUMNS) if bill_rows else pd.DataFrame(columns=BILLS_COLUMNS)
    events_df = (pd.DataFrame(event_rows) if event_rows
                 else pd.DataFrame(columns=["area_id", "date", "metric", "bill_id", "event_type", "chamber", "value"]))
    return bills_df, events_df
