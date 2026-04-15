"""
CRE keyword *hint* utility (not a gate).

The 20x Anthropic plan makes AI enrichment on every fetched bill affordable, so the
connectors do NOT use this to filter out bills before AI runs. Instead, keyword hits
are stored in the `cre_keywords_hit` column as a display aid (quick "why is this in the
data?" breadcrumb) and as a cache warmer for the AI prompt.

The canonical keyword list lives in etl-base/etl/legislation/cre_keywords.yml so both
the ETL wrapper and this repo can read the same source.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Tuple

import yaml


DEFAULT_KEYWORDS = [
    # zoning / land use
    "zoning", "rezoning", "land use", "land development", "subdivision", "setback",
    "density bonus", "mixed-use", "entitlement", "comprehensive plan",
    # housing tenure / rent / eviction
    "rent control", "rent stabilization", "eviction", "habitability", "tenant",
    "landlord", "lease", "security deposit", "rental assistance",
    # property tax / assessment
    "property tax", "ad valorem", "mill levy", "transfer tax", "tax increment", "tif",
    "assessment limit", "homestead", "opportunity zone",
    # short-term rental
    "short-term rental", "short term rental", "str", "airbnb", "vrbo", "vacation rental",
    # development / construction
    "building code", "impact fee", "permitting", "historic preservation", "environmental review",
    "condemnation", "eminent domain", "inclusionary", "affordable housing", "accessory dwelling", "adu",
    # real property / finance
    "mortgage", "foreclosure", "real property", "deed restriction", "title", "hoa",
    "property insurance", "flood zone", "commercial real estate",
    # asset classes
    "warehouse", "industrial", "multifamily", "self storage",
]


@lru_cache(maxsize=4)
def load_keywords(yaml_path: str | None = None) -> Tuple[str, ...]:
    """Load keywords from YAML if available; otherwise fall back to DEFAULT_KEYWORDS."""
    path = Path(yaml_path) if yaml_path else None
    if path and path.exists():
        try:
            with path.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            kws = data.get("keywords") or []
            if kws:
                return tuple(str(k).lower() for k in kws)
        except Exception:
            pass
    return tuple(k.lower() for k in DEFAULT_KEYWORDS)


def _compile(keywords: Iterable[str]) -> re.Pattern:
    escaped = [re.escape(k) for k in keywords]
    # Word-boundary on alphanumeric edges only — allows "mixed-use" etc.
    pattern = r"(?<![\w])(?:" + "|".join(escaped) + r")(?![\w])"
    return re.compile(pattern, re.IGNORECASE)


def score_text(text: str, keywords: Iterable[str] | None = None) -> list[str]:
    """Return list of keyword hits in text. Case-insensitive."""
    if not text:
        return []
    kws = tuple(keywords) if keywords else load_keywords()
    if not kws:
        return []
    matches = _compile(kws).findall(text)
    seen, out = set(), []
    for m in matches:
        ml = m.lower()
        if ml not in seen:
            seen.add(ml)
            out.append(ml)
    return out


def is_cre_relevant(title: str | None, description: str | None = None,
                     subjects: Iterable[str] | None = None,
                     keywords: Iterable[str] | None = None) -> tuple[bool, list[str]]:
    blob = " ".join([title or "", description or "", " ".join(subjects or [])])
    hits = score_text(blob, keywords)
    return bool(hits), hits
