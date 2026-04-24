"""
config.py — Central configuration for Legislative Tracker.

Shared design tokens with analytics-workbench and contract-tracker.
Supports both local development (reads ../etl-base/parquet/) and Azure (az://etl/).
"""

import os
import logging
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ============================
# LOGGING
# ============================
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

# ============================
# AZURE CONFIGURATION
# ============================
USE_AZURE = os.getenv("USE_AZURE", "false").lower() == "true"
AZURE_STORAGE_ACCOUNT = os.getenv("AZURE_STORAGE_ACCOUNT", "stdp58902")
AZURE_CONTAINER = os.getenv("AZURE_CONTAINER", "etl")
KEY_VAULT_NAME = os.getenv("KEY_VAULT_NAME", "kv-data-registry-dev")

if USE_AZURE:
    from azure.identity import DefaultAzureCredential
    AZURE_STORAGE_OPTIONS = {
        "account_name": AZURE_STORAGE_ACCOUNT,
        "credential": DefaultAzureCredential(),
    }
else:
    AZURE_STORAGE_OPTIONS = None

# ============================
# PATHS
# ============================
BASE_DIR = Path(__file__).parent.absolute()

if USE_AZURE:
    STORAGE_PREFIX = f"az://{AZURE_CONTAINER}"
    BILLS_PARQUET = f"{STORAGE_PREFIX}/parquet/market/legislation/bills.parquet"
    BILL_EVENTS_PARQUET = f"{STORAGE_PREFIX}/parquet/market/legislation/bill_events.parquet"
    METRICS_PARQUET = f"{STORAGE_PREFIX}/parquet/market/legislation/metrics.parquet"
    AREAS_PATH = f"{STORAGE_PREFIX}/processed/geography/areas.csv"
    LEGISLATION_RAW_PREFIX = "legislation/raw"   # blob prefix, not a full path
    LEGISLATION_TEXT_PREFIX = "legislation/text"
    LEGISLATION_STATE_PREFIX = "legislation/_state"
else:
    ETL_BASE_DIR = BASE_DIR.parent / "etl-base"
    BILLS_PARQUET = ETL_BASE_DIR / "parquet" / "market" / "legislation" / "bills.parquet"
    BILL_EVENTS_PARQUET = ETL_BASE_DIR / "parquet" / "market" / "legislation" / "bill_events.parquet"
    METRICS_PARQUET = ETL_BASE_DIR / "parquet" / "market" / "legislation" / "metrics.parquet"
    AREAS_PATH = ETL_BASE_DIR / "processed" / "geography" / "areas.csv"
    LEGISLATION_RAW_PREFIX = "legislation/raw"
    LEGISLATION_TEXT_PREFIX = "legislation/text"
    LEGISLATION_STATE_PREFIX = "legislation/_state"

# ============================
# COLORS & STYLES (shared tokens)
# ============================
BRAND_COLOR = "#074070"
BRAND_LIGHT = "#B6D6EF"
ACCENT_COLOR = "#589BD5"

GRAY_50 = "#f9fafb"
GRAY_100 = "#f3f4f6"
GRAY_200 = "#e5e7eb"
GRAY_300 = "#d1d5db"
GRAY_500 = "#6b7280"
GRAY_700 = "#374151"
GRAY_900 = "#111827"

CARD_STYLE = {
    "background": "#fff",
    "borderRadius": "8px",
    "boxShadow": "0 1px 3px rgba(0,0,0,0.1)",
    "padding": "16px",
}

POSITIVE_COLOR = "#059669"
NEGATIVE_COLOR = "#dc2626"
WARNING_COLOR = "#d97706"
INFO_COLOR = "#3b82f6"

# ============================
# LAYOUT CONSTANTS
# ============================
SIDEBAR_WIDTH = "320px"
NAV_HEIGHT = "56px"

# ============================
# DOMAIN CONSTANTS
# ============================
STATES = ["CO", "TX", "FL", "UT", "VA", "MD", "NV", "TN", "GA", "AZ", "ID"]

# Canonical timeline stages. Exactly four, mutually exclusive — these are the
# only stage names anything in the UI should ever render.
#   introduced  — bill was introduced (purple)
#   passed      — passed BOTH chambers (blue)
#   law         — signed into law by the governor (green) — final state
#   killed      — vetoed / died / failed (gray) — final state
STATUS_GROUPS = [
    ("introduced",  "Introduced"),
    ("passed",      "Awaiting Governor"),
    ("law",         "Became Law"),
    ("killed",      "Killed"),
]
# Only passing BOTH chambers counts as "Awaiting Governor". First-chamber
# passage is still "Introduced" from the user's perspective (the bill is
# still inside the legislature).
STATUS_GROUP = {
    "introduced":     "introduced",
    "amended":        "introduced",
    "in_committee":   "introduced",
    "committee":      "introduced",
    "passed_chamber": "introduced",
    "passed":         "passed",
    "signed":         "law",
    "enacted":        "law",
    "vetoed":         "killed",
    "failed":         "killed",
}
STAGE_ORDER = ["introduced", "passed", "law", "killed"]
STAGE_LABELS = {
    "introduced": "Intro",
    "passed":     "Awaiting Gov",
    "law":        "Became law",
    "killed":     "Killed",
}

# Raw status codes → UI label (for the modal "Status: X" meta line).
STATUS_BUCKETS = [
    ("enacted",         "Became law",         "#2E7D32"),
    ("signed",          "Became law",         "#2E7D32"),
    ("passed",          "Awaiting Governor",  "#1B5E83"),
    ("passed_chamber",  "Introduced",         "#6A4C93"),
    ("in_committee",    "Introduced",         "#6A4C93"),
    ("committee",       "Introduced",         "#6A4C93"),
    ("introduced",      "Introduced",         "#6A4C93"),
    ("amended",         "Introduced",         "#6A4C93"),
    ("vetoed",          "Killed",             "#999999"),
    ("failed",          "Killed",             "#999999"),
]
STATUS_COLOR = {code: color for code, _label, color in STATUS_BUCKETS}
STATUS_LABEL = {code: label for code, label, _c in STATUS_BUCKETS}

# Legend shown in the title bar — the four canonical stages.
LEGEND = [
    ("Introduced",       "#6A4C93"),
    ("Awaiting Gov",     "#1B5E83"),
    ("Became law",       "#2E7D32"),
    ("Killed",           "#999999"),
]

# Direction legend — shown next to the status legend in the title bar so the
# user knows what the ▲ ▼ ◆ glyphs on cards and in the right sidebar mean.
# Framed from the MF owner-operator lens (not a developer).
DIRECTION_LEGEND = [
    ("Favorable for MF owners", "▲", "#16a34a"),
    ("Adverse for MF owners",   "▼", "#ef4444"),
    ("Mixed impact",            "◆", "#d97706"),
]

# Backwards-compatible alias used by a couple of older render paths.
EVENT_COLORS = STATUS_COLOR

# Milestone CRE category taxonomy. The snake_case value is the canonical
# identifier stored in `ai_categories` and used for filtering; the display
# label is shown to the user everywhere in the UI. Never surface the
# snake_case form in the app.
CRE_CATEGORIES = [
    ("zoning",                "Zoning"),
    ("land_use",              "Land Use"),
    ("adu",                   "ADU"),
    ("permitting",            "Permitting"),
    ("impact_fee",            "Impact Fees"),
    ("historic_preservation", "Historic Preservation"),
    ("property_tax",          "Property Tax"),
    ("transfer_tax",          "Transfer Tax"),
    ("tif",                   "Tax Increment Financing"),
    ("opportunity_zone",      "Opportunity Zones"),
    ("rent_control",          "Rent Control"),
    ("eviction",              "Eviction"),
    ("habitability",          "Habitability"),
    ("affordable_housing",    "Affordable Housing"),
    ("short_term_rental",     "Short-Term Rentals"),
    ("building_code",         "Building Code"),
    ("eminent_domain",        "Eminent Domain"),
    ("mortgage",              "Mortgage"),
    ("foreclosure",           "Foreclosure"),
    ("hoa",                   "HOA"),
    ("insurance",             "Insurance"),
]
CRE_SUBJECTS = [code for code, _label in CRE_CATEGORIES]   # backwards-compat
CATEGORY_LABEL = {code: label for code, label in CRE_CATEGORIES}
