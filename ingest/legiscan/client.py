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
import io
import json
import logging
import pathlib
import re
import time
import zipfile
from datetime import datetime, timedelta
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
    "Postpone Indefinitely": "failed",
    "Postponed Indefinitely": "failed",
    "Withdrawn": "failed",
    "Amended": "amended",
    "Substituted": "amended",
}

STATUS_CODE_MAP = {
    # LegiScan numeric status codes (per their API docs):
    # 1 Introduced, 2 Engrossed (passed first chamber), 3 Enrolled (passed both
    # chambers, awaiting governor), 4 Passed (signed into law), 5 Vetoed,
    # 6 Failed/Died/Postponed Indefinitely.
    1: "introduced",
    2: "passed_chamber",
    3: "passed",
    4: "enacted",
    5: "vetoed",
    6: "failed",
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
        # GUARD: per-bill API calls burn credits at O(bills). The previous run
        # of this code burned an entire credit allotment in under 5 minutes.
        # Bulk dataset API (get_dataset_list + get_dataset) is the supported path.
        # If you really need per-bill, set LEGISCAN_ALLOW_PERBILL=1 explicitly.
        import os
        if not os.environ.get("LEGISCAN_ALLOW_PERBILL"):
            raise LegiScanError(
                "Per-bill getBill API call blocked to prevent credit burn. "
                "Use fetch_state_bills() (bulk dataset API) instead. "
                "To override, set LEGISCAN_ALLOW_PERBILL=1 in the environment."
            )
        return self._call("getBill", id=bill_id).get("bill", {})

    def get_bill_text(self, doc_id: int) -> dict:
        import os
        if not os.environ.get("LEGISCAN_ALLOW_PERBILL"):
            raise LegiScanError(
                "Per-bill getBillText API call blocked to prevent credit burn. "
                "Bulk ZIPs already include text references; download via state_link instead. "
                "To override, set LEGISCAN_ALLOW_PERBILL=1 in the environment."
            )
        return self._call("getBillText", id=doc_id).get("text", {})

    def get_dataset_list(self, state: str) -> list[dict]:
        return self._call("getDatasetList", state=state).get("datasetlist", [])

    def get_dataset(self, session_id: int, access_key: str) -> bytes:
        """Download the bulk ZIP for a session. Returns raw ZIP bytes."""
        data = self._call("getDataset", id=session_id, access_key=access_key)
        ds = data.get("dataset", {})
        zip_b64 = ds.get("zip") or ""
        if not zip_b64:
            raise LegiScanError(f"getDataset returned no zip for session {session_id}")
        return base64.b64decode(zip_b64)


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


def _index_votes_from_zip(zf: zipfile.ZipFile) -> dict[int, list[dict]]:
    """Pre-index every vote JSON in the ZIP by integer bill_id — one pass.
    Returns {legiscan_bill_id: [roll_call_summary, ...]} sorted by date.
    """
    index: dict[int, list[dict]] = {}
    for name in zf.namelist():
        if not (name.endswith(".json") and "/vote/" in name.lower()):
            continue
        try:
            rc = json.loads(zf.read(name)).get("roll_call", {})
        except Exception:
            continue
        bid = int(rc.get("bill_id") or 0)
        if not bid:
            continue
        ch = rc.get("chamber") or ""
        chamber = "House" if ch == "H" else ("Senate" if ch == "S" else ch)
        index.setdefault(bid, []).append({
            "chamber": chamber,
            "date": rc.get("date") or "",
            "desc": rc.get("desc") or "",
            "yea": int(rc.get("yea") or 0),
            "nay": int(rc.get("nay") or 0),
            "nv": int(rc.get("nv") or 0),
            "absent": int(rc.get("absent") or 0),
            "passed": int(rc.get("passed") or 0),
            "result": "Passed" if int(rc.get("passed") or 0) == 1 else "Failed",
        })
    for bid in index:
        index[bid].sort(key=lambda r: r.get("date") or "")
    return index


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
        rows.append(event_row(area_id, h.get("date"), bill_id, etype, chamber,
                               action_text=action))

    # NOTE: we used to synthesize a separate "enacted" event at a
    # parsed-from-text effective date. That produced junk (e.g. 2020 rows for
    # 2025 bills when the parser misfired) and the UI kept rendering a
    # confusing "In Effect" card that didn't match the history. The "signed"
    # history event already represents "signed into law" — we treat that as
    # the final stage in the UI (via STATUS_GROUP: signed → enacted).
    # Synthesize a 'failed' event when bill status is 6 and history has no
    # explicit failed action, so the timeline can still show it.
    final_status = _current_status(bill)
    if final_status == "failed" and not any(r.get("event_type") == "failed" for r in rows):
        status_date = bill.get("status_date") or ""
        if status_date:
            rows.append(event_row(area_id, status_date, bill_id, "failed", None))
    return rows


def _current_status(bill: dict) -> str:
    code = bill.get("status")
    try:
        code_int = int(code) if code is not None else None
    except (TypeError, ValueError):
        code_int = None
    return STATUS_CODE_MAP.get(code_int, "introduced")


RESOLUTION_RE = re.compile(r"^(SJR|HJR|SR|HR|SJM|HJM|SCR|HCR|SM|HM)\d", re.I)


def _bill_from_json(
    bill: dict,
    state: str,
    area_id: int,
    session_name: str,
    votes_by_bill: dict | None = None,
) -> tuple[dict | None, list[dict]]:
    """Parse a single LegiScan bill JSON into a bills-row dict + event rows.
    Returns (None, []) if the bill should be skipped (e.g. resolutions).

    Stashes bill.state into the dict so _extract_history_events can locate
    the local PDF for effective-date parsing. Pulls vote roll-calls from
    a pre-indexed dict (built once per ZIP in fetch_state_from_zips).
    """
    bill_number = bill.get("bill_number") or ""
    if RESOLUTION_RE.match(bill_number):
        return None, []

    # bill_id must include LegiScan's globally-unique integer bill_id — bill_number
    # repeats every session (CO 2024 HB1001 vs CO 2025 HB1001 vs CO 2026 HB1001 all
    # share "HB1001"), so keying by bill_number causes cross-session collisions and
    # loses most of the current-session bills to dedupe.
    legiscan_id = bill.get("bill_id")
    if not legiscan_id:
        return None, []
    bill_id = f"legiscan:{state}:{legiscan_id}"
    title = bill.get("title") or ""
    description = bill.get("description") or ""
    _, hits = is_cre_relevant(title, description, _extract_subjects(bill))

    # Stash state on bill dict so the effective-date helper can find the PDF.
    bill["state"] = state

    votes_json = "[]"
    if votes_by_bill is not None:
        rolls = votes_by_bill.get(int(legiscan_id)) or []
        if rolls:
            votes_json = json.dumps(rolls, separators=(",", ":"))

    row = {
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
        "sponsors_json": json.dumps(_extract_sponsors(bill), separators=(",", ":")),
        "subjects_json": json.dumps(_extract_subjects(bill), separators=(",", ":")),
        "url": bill.get("state_link") or bill.get("url") or "",
        "text_blob_path": "",
        "cre_relevant": None,
        "cre_keywords_hit": ";".join(hits),
        "ai_summary": "",
        "ai_risk_score": None,
        "ai_risk_breakdown_json": "",
        "ai_risk_rationale_json": "",
        "ai_direction_rationale": "",
        "impact_direction": "",
        "ai_categories": "",
        "ai_model_version": "",
        "ai_analyzed_date": "",
        "votes_json": votes_json,
        "last_updated": datetime.utcnow().isoformat(timespec="seconds"),
    }
    events = _extract_history_events(bill, bill_id, area_id)
    return row, events


def fetch_state_from_zips(
    state: str,
    area_id: int,
    zips_dir,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Ingest bills from manually-downloaded LegiScan dataset ZIPs.

    Parses each `*.zip` under `zips_dir` (typically `etl-base/temp/legislation/zips/<STATE>/`)
    using the same bill JSON -> row logic as the API path. No blob uploads —
    the local ZIPs themselves are the audit trail; bills we filter out (or don't
    ultimately keep after AI relevance scoring) shouldn't consume blob storage.
    Re-parsing a specific bill later is trivial (read the ZIP).
    """
    import pathlib
    zips_dir = pathlib.Path(zips_dir)
    if not zips_dir.exists():
        logger.warning("zips_dir does not exist: %s", zips_dir)
        return pd.DataFrame(columns=BILLS_COLUMNS), pd.DataFrame(
            columns=["area_id", "date", "metric", "bill_id", "event_type", "chamber", "value"])

    zip_paths = sorted(zips_dir.glob("*.zip"))
    if not zip_paths:
        logger.warning("No .zip files found in %s", zips_dir)
        return pd.DataFrame(columns=BILLS_COLUMNS), pd.DataFrame(
            columns=["area_id", "date", "metric", "bill_id", "event_type", "chamber", "value"])

    bill_rows: list[dict] = []
    event_rows: list[dict] = []
    seen = set()

    for zpath in zip_paths:
        logger.info("Parsing %s", zpath.name)
        with zipfile.ZipFile(zpath) as zf:
            # Derive session name from the ZIP filename if we can — LegiScan's
            # download naming is typically `CO_2025-2025_Regular_Session.zip`.
            session_name = zpath.stem.replace("_", " ")
            bill_files = [n for n in zf.namelist()
                          if n.endswith(".json") and "/bill/" in n.lower()]
            logger.info("  %d bill JSONs in %s", len(bill_files), zpath.name)

            # Index all roll-call votes in this ZIP once, then look up per bill.
            votes_by_bill = _index_votes_from_zip(zf)
            if votes_by_bill:
                logger.info("  %d roll-call votes indexed", sum(len(v) for v in votes_by_bill.values()))

            for name in bill_files:
                try:
                    raw = json.loads(zf.read(name))
                except (json.JSONDecodeError, KeyError) as exc:
                    logger.debug("Bad JSON in %s: %s", name, exc)
                    continue

                bill = raw.get("bill", raw)
                # Prefer the session_name from the bill payload when present
                # (keeps row's session matching what the bill itself says).
                sess = (bill.get("session") or {}).get("session_name") or session_name
                row, events = _bill_from_json(bill, state, area_id, sess, votes_by_bill=votes_by_bill)
                if row is None:
                    continue

                bill_id = row["bill_id"]
                if bill_id in seen:
                    continue  # cross-session duplicate in this batch — keep first
                seen.add(bill_id)

                bill_rows.append(row)
                event_rows.extend(events)

    bills_df = pd.DataFrame(bill_rows, columns=BILLS_COLUMNS) if bill_rows else pd.DataFrame(columns=BILLS_COLUMNS)
    events_df = (pd.DataFrame(event_rows) if event_rows
                 else pd.DataFrame(columns=["area_id", "date", "metric", "bill_id", "event_type", "chamber", "value"]))
    logger.info("Parsed %d bills, %d events from %d ZIP(s) for %s",
                len(bill_rows), len(event_rows), len(zip_paths), state)
    return bills_df, events_df


def fetch_state_bills(
    state: str,
    area_id: int,
    session_ids: Iterable[int] | None = None,
    client: LegiScanClient | None = None,
    max_sessions: int = 5,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Fetch bills via bulk dataset downloads (one API call per session).

    Uses getDatasetList + getDataset — each session is a single ZIP containing
    every bill as a JSON file. This is O(sessions) API calls, not O(bills).
    Resolutions / memorials are filtered out by bill-number prefix.

    Returns (bills_df, events_df) following `ingest/schema.py` columns.
    Raw per-bill JSON is written to blob; no local files are created.
    """
    client = client or LegiScanClient()
    storage = get_storage()

    datasets = client.get_dataset_list(state)
    if not datasets:
        logger.warning("No datasets returned for %s", state)
        return pd.DataFrame(columns=BILLS_COLUMNS), pd.DataFrame(
            columns=["area_id", "date", "metric", "bill_id", "event_type", "chamber", "value"])

    # Sort by year descending; take the most recent N sessions.
    if isinstance(datasets, dict):
        datasets = list(datasets.values())
    datasets = [d for d in datasets if isinstance(d, dict) and d.get("session_id")]
    datasets.sort(key=lambda d: d.get("year_end") or d.get("year_start") or 0, reverse=True)
    if session_ids is not None:
        wanted = set(session_ids)
        datasets = [d for d in datasets if d.get("session_id") in wanted]
    else:
        datasets = datasets[:max_sessions]

    cursor = _load_cursor(state)
    new_cursor = dict(cursor)

    bill_rows: list[dict] = []
    event_rows: list[dict] = []
    month = datetime.utcnow().strftime("%Y-%m")

    for ds in datasets:
        session_id = ds.get("session_id")
        access_key = ds.get("access_key") or ""
        session_name = ds.get("session_name") or str(ds.get("year_start"))
        dataset_hash = ds.get("dataset_hash") or ""

        if cursor.get(f"ds:{session_id}") == dataset_hash and dataset_hash:
            logger.info("Session %s unchanged (hash match), skipping", session_name)
            continue

        logger.info("Downloading bulk dataset for %s (session %s)", session_name, session_id)
        try:
            zip_bytes = client.get_dataset(session_id, access_key)
        except LegiScanError as exc:
            logger.warning("getDataset failed for session %s: %s", session_id, exc)
            continue

        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            bill_files = [n for n in zf.namelist() if n.endswith(".json") and "/bill/" in n.lower()]
            logger.info("  %d bill JSONs in ZIP for %s", len(bill_files), session_name)

            for name in bill_files:
                try:
                    raw = json.loads(zf.read(name))
                except (json.JSONDecodeError, KeyError) as exc:
                    logger.debug("Bad JSON in %s: %s", name, exc)
                    continue

                bill = raw.get("bill", raw)
                row, events = _bill_from_json(bill, state, area_id, session_name)
                if row is None:
                    continue

                bill_id = row["bill_id"]
                raw_blob = f"legislation/raw/legiscan/{state}/{month}/{bill_id.replace(':', '_')}.json.gz"
                try:
                    storage.upload_json_gz(raw_blob, bill)
                except Exception as exc:
                    logger.debug("Blob write failed for %s: %s", bill_id, exc)

                bill_rows.append(row)
                event_rows.extend(events)

        new_cursor[f"ds:{session_id}"] = dataset_hash

    _save_cursor(state, new_cursor)

    bills_df = pd.DataFrame(bill_rows, columns=BILLS_COLUMNS) if bill_rows else pd.DataFrame(columns=BILLS_COLUMNS)
    events_df = (pd.DataFrame(event_rows) if event_rows
                 else pd.DataFrame(columns=["area_id", "date", "metric", "bill_id", "event_type", "chamber", "value"]))
    logger.info("Fetched %d bills, %d events for %s across %d sessions",
                len(bill_rows), len(event_rows), state, len(datasets))
    return bills_df, events_df
