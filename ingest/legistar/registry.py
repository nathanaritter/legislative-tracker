"""
Per-jurisdiction LegiStar registry.

Each entry points at a Granicus LegiStar OData tenant. The `matter_type_ids` tuple filters
to legislation-like matter types — these vary per tenant and must be discovered once by
querying `/MatterTypes`, then pinned here.

Start small (Denver, Austin, Nashville) and grow as each jurisdiction's matter types are
pinned down. Jurisdictions without a LegiStar portal should be added as `disabled=True`
placeholders rather than assumed to exist.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator

from ingest.legistar.base import LegistarConfig, LegistarClient


@dataclass
class RegistryEntry:
    cfg: LegistarConfig
    enabled: bool = True
    notes: str = ""


# ----------------------------------------------------------------------------
# Seed jurisdictions. area_ids are placeholders (0) until rows for each city/county
# are added to etl-base/processed/geography/areas.csv.
# matter_type_ids default to empty → accept all matter types. Pin after first run.
# ----------------------------------------------------------------------------
REGISTRY: dict[str, RegistryEntry] = {
    "denver": RegistryEntry(LegistarConfig(
        slug="denver",
        jurisdiction_name="Denver, CO",
        state="CO",
        area_id=0,
        jurisdiction_level="city",
        matter_type_ids=tuple(),
    )),
    "austin": RegistryEntry(LegistarConfig(
        slug="austin",
        jurisdiction_name="Austin, TX",
        state="TX",
        area_id=0,
        jurisdiction_level="city",
        matter_type_ids=tuple(),
    )),
    "nashville": RegistryEntry(LegistarConfig(
        slug="nashville",
        jurisdiction_name="Nashville-Davidson, TN",
        state="TN",
        area_id=0,
        jurisdiction_level="city",
        matter_type_ids=tuple(),
    )),

    # --- Placeholders for build-out (disabled until verified) ----------------
    "miamidade": RegistryEntry(LegistarConfig("miamidade", "Miami-Dade County, FL", "FL", 0, "county", ()), enabled=False,
                                notes="Confirm LegiStar tenant slug before enabling."),
    "phoenix": RegistryEntry(LegistarConfig("phoenix", "Phoenix, AZ", "AZ", 0, "city", ()), enabled=False),
    "slco": RegistryEntry(LegistarConfig("slco", "Salt Lake County, UT", "UT", 0, "county", ()), enabled=False),
    "fairfax": RegistryEntry(LegistarConfig("fairfaxcounty", "Fairfax County, VA", "VA", 0, "county", ()), enabled=False),
    "montgomerymd": RegistryEntry(LegistarConfig("montgomerymd", "Montgomery County, MD", "MD", 0, "county", ()), enabled=False),
    "lasvegas": RegistryEntry(LegistarConfig("lasvegas", "Las Vegas, NV", "NV", 0, "city", ()), enabled=False),
    "clarkcountynv": RegistryEntry(LegistarConfig("clarkcountynv", "Clark County, NV", "NV", 0, "county", ()), enabled=False),
    "atlanta": RegistryEntry(LegistarConfig("atlanta", "Atlanta, GA", "GA", 0, "city", ()), enabled=False),
    "boise": RegistryEntry(LegistarConfig("boise", "Boise, ID", "ID", 0, "city", ()), enabled=False),
}


def enabled_entries() -> Iterator[RegistryEntry]:
    for entry in REGISTRY.values():
        if entry.enabled:
            yield entry


def make_client(slug: str) -> LegistarClient:
    entry = REGISTRY.get(slug)
    if entry is None:
        raise KeyError(f"Unknown LegiStar jurisdiction: {slug}")
    return LegistarClient(entry.cfg)
