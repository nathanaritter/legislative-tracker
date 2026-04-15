"""
Abstract LegiStar / Granicus client base. Each jurisdiction's OData endpoint is wrapped
by a subclass in ingest/legistar/connectors/. The registry wires slug → client.

Granicus LegiStar exposes an OData v3 API:
    https://webapi.legistar.com/v1/{client}/Matters
    https://webapi.legistar.com/v1/{client}/MatterHistories
    https://webapi.legistar.com/v1/{client}/MatterSponsors
    https://webapi.legistar.com/v1/{client}/MatterAttachments

Matter types vary per jurisdiction; subclasses override MATTER_TYPE_FILTER to scope to
the legislation-like matter types (ordinances, resolutions, bills).

Raw per-matter JSON is written to blob, never to local disk.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

import pandas as pd
import requests

from ingest.schema import BILLS_COLUMNS, event_row
from ingest.legiscan.cre_filter import is_cre_relevant
from services.storage import get_client as get_storage


logger = logging.getLogger(__name__)
LEGISTAR_BASE = "https://webapi.legistar.com/v1"


# Map LegiStar MatterHistoryActionName fragments → our event_type vocabulary.
LEGISTAR_ACTION_MAP = {
    "introduced": "introduced",
    "filed": "introduced",
    "referred to committee": "in_committee",
    "committee": "committee",
    "reported": "committee",
    "amended": "amended",
    "passed": "passed",
    "adopted": "passed",
    "approved": "signed",
    "signed": "signed",
    "enacted": "enacted",
    "effective": "enacted",
    "vetoed": "vetoed",
    "failed": "failed",
    "withdrawn": "failed",
}


@dataclass
class LegistarConfig:
    slug: str                         # Legistar client code, e.g. "denver"
    jurisdiction_name: str            # Display name
    state: str                        # 2-letter state code
    area_id: int                      # joins to areas.csv
    jurisdiction_level: str           # city | county
    matter_type_ids: tuple[int, ...]  # which matter type IDs count as legislation (varies per client)


class LegistarClient:
    def __init__(self, cfg: LegistarConfig, timeout: int = 30):
        self.cfg = cfg
        self.timeout = timeout
        self._session = requests.Session()

    def _url(self, path: str) -> str:
        return f"{LEGISTAR_BASE}/{self.cfg.slug}/{path}"

    def _get(self, path: str, **params) -> list[dict]:
        resp = self._session.get(self._url(path), params=params, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json() or []

    def list_matters(self, since: datetime | None = None) -> list[dict]:
        flt = None
        if since:
            flt = f"MatterIntroDate ge datetime'{since.strftime('%Y-%m-%dT00:00:00')}'"
        params = {}
        if flt:
            params["$filter"] = flt
        return self._get("Matters", **params)

    def matter_history(self, matter_id: int) -> list[dict]:
        return self._get(f"Matters/{matter_id}/Histories")

    def matter_sponsors(self, matter_id: int) -> list[dict]:
        return self._get(f"Matters/{matter_id}/Sponsors")

    def matter_attachments(self, matter_id: int) -> list[dict]:
        return self._get(f"Matters/{matter_id}/Attachments")


# ----------------------------------------------------------------------------
# Normalization: LegiStar JSON → bills_df + events_df rows.
# ----------------------------------------------------------------------------

def _event_type(action_name: str) -> str | None:
    if not action_name:
        return None
    lower = action_name.lower()
    for frag, et in LEGISTAR_ACTION_MAP.items():
        if frag in lower:
            return et
    return None


def _current_status_from_history(history: list[dict]) -> str:
    """Pick the latest mapped action as current status, fallback to 'introduced'."""
    for h in sorted(history, key=lambda x: x.get("MatterHistoryActionDate", ""), reverse=True):
        et = _event_type(h.get("MatterHistoryActionName") or "")
        if et:
            return et
    return "introduced"


def fetch_jurisdiction_bills(
    client: LegistarClient,
    since: datetime | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    cfg = client.cfg
    storage = get_storage()
    bill_rows: list[dict] = []
    event_rows: list[dict] = []

    matters = client.list_matters(since=since)
    wanted_types = set(cfg.matter_type_ids)

    for m in matters:
        matter_type_id = m.get("MatterTypeId")
        if wanted_types and matter_type_id not in wanted_types:
            continue

        matter_id = m.get("MatterId")
        if matter_id is None:
            continue

        number = m.get("MatterFile") or m.get("MatterNumber") or str(matter_id)
        bill_id = f"legistar:{cfg.slug}:{number}"
        title = m.get("MatterTitle") or m.get("MatterName") or ""
        description = m.get("MatterEXText5") or m.get("MatterBodyName") or ""

        # Keyword hits are a display hint only — CRE relevance is decided by the AI batch step.
        _, hits = is_cre_relevant(title, description, subjects=None)

        history = []
        sponsors_list = []
        attachments = []
        try:
            history = client.matter_history(matter_id)
            sponsors_list = client.matter_sponsors(matter_id)
            attachments = client.matter_attachments(matter_id)
        except Exception as exc:
            logger.warning("Fetch child records failed for %s %s: %s", cfg.slug, number, exc)

        raw_bundle = {"matter": m, "history": history, "sponsors": sponsors_list, "attachments": attachments}
        month = datetime.utcnow().strftime("%Y-%m")
        raw_blob = f"legislation/raw/legistar/{cfg.slug}/{month}/{bill_id.replace(':', '_')}.json.gz"
        try:
            storage.upload_json_gz(raw_blob, raw_bundle)
        except Exception as exc:
            logger.warning("Raw blob write failed for %s: %s", bill_id, exc)

        sponsors_norm = [{
            "name": s.get("MatterSponsorName"),
            "party": None,
            "role": s.get("MatterSponsorBodyName"),
            "district": None,
        } for s in sponsors_list]

        text_blob_path = ""
        if attachments:
            # Just record the canonical url; downloading the attachment is left to a
            # future enhancement (attachments often need a second HTTP hop).
            for a in attachments:
                if a.get("MatterAttachmentHyperlink"):
                    text_blob_path = a["MatterAttachmentHyperlink"]
                    break

        bill_rows.append({
            "bill_id": bill_id,
            "source": "legistar",
            "state": cfg.state,
            "area_id": cfg.area_id,
            "jurisdiction_level": cfg.jurisdiction_level,
            "jurisdiction_name": cfg.jurisdiction_name,
            "bill_number": number,
            "session": m.get("MatterAgendaDate", "")[:4] if m.get("MatterAgendaDate") else "",
            "title": title,
            "introduced_date": m.get("MatterIntroDate", "")[:10] if m.get("MatterIntroDate") else "",
            "last_action_date": (history[0].get("MatterHistoryActionDate", "")[:10] if history else ""),
            "current_status": _current_status_from_history(history) if history else "introduced",
            "sponsors_json": json.dumps(sponsors_norm, separators=(",", ":")),
            "subjects_json": json.dumps([], separators=(",", ":")),
            "url": f"https://{cfg.slug}.legistar.com/LegislationDetail.aspx?ID={matter_id}",
            "text_blob_path": text_blob_path,
            "cre_relevant": None,          # set by AI enrichment
            "cre_keywords_hit": ";".join(hits),
            "ai_summary": "",
            "ai_risk_score": None,
            "ai_risk_breakdown_json": "",
            "ai_model_version": "",
            "last_updated": datetime.utcnow().isoformat(timespec="seconds"),
        })

        for h in history:
            et = _event_type(h.get("MatterHistoryActionName") or "")
            if not et:
                continue
            event_rows.append(event_row(
                cfg.area_id,
                h.get("MatterHistoryActionDate"),
                bill_id,
                et,
                chamber=h.get("MatterHistoryActionBodyName"),
            ))

    bills_df = pd.DataFrame(bill_rows, columns=BILLS_COLUMNS) if bill_rows else pd.DataFrame(columns=BILLS_COLUMNS)
    events_df = (pd.DataFrame(event_rows) if event_rows
                 else pd.DataFrame(columns=["area_id", "date", "metric", "bill_id", "event_type", "chamber", "value"]))
    return bills_df, events_df
