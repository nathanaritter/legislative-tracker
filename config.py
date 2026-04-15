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

# Four consolidated status buckets shown in the UI. Each raw LegiScan / LegiStar
# status maps into one of these via STATUS_GROUP.
STATUS_GROUPS = [
    ("introduced",  "Introduced"),
    ("committee",   "In Committee"),
    ("passed",      "Passed Legislature"),
    ("enacted",     "In Effect"),
    ("failed",      "Failed / Vetoed"),
]
STATUS_GROUP = {
    "introduced":     "introduced",
    "amended":        "introduced",
    # Committee events roll up into the Intro bucket — we don't show "Cmte" as
    # its own stage. (Raw event_type still stored for audit.)
    "in_committee":   "introduced",
    "committee":      "introduced",
    "passed_chamber": "passed",
    "passed":         "passed",
    "signed":         "passed",
    "enacted":        "enacted",
    "vetoed":         "failed",
    "failed":         "failed",
}
# Stages we render on the timeline. Committee intentionally absent.
STAGE_ORDER = ["introduced", "passed", "enacted"]
STAGE_LABELS = {
    "introduced": "Intro",
    "passed":     "Passed",
    "enacted":    "Effect",
    "failed":     "Failed",
}

# Status buckets + colors mirror the Milestone PPTX regulatory timeline deck
# (etl-base-adjacent design; see "update timeline/card_templates.md").
STATUS_BUCKETS = [
    ("enacted",         "In Effect",              "#2E7D32"),
    ("signed",          "Signed / Passed Leg.",   "#1B5E83"),
    ("passed",          "Signed / Passed Leg.",   "#1B5E83"),
    ("passed_chamber",  "Signed / Passed Leg.",   "#1B5E83"),
    ("in_committee",    "Introduced / Committee", "#6A4C93"),
    ("committee",       "Introduced / Committee", "#6A4C93"),
    ("introduced",      "Introduced / Committee", "#6A4C93"),
    ("amended",         "Introduced / Committee", "#6A4C93"),
    ("vetoed",          "Vetoed / Killed",        "#999999"),
    ("failed",          "Vetoed / Killed",        "#999999"),
]
STATUS_COLOR = {code: color for code, _label, color in STATUS_BUCKETS}
STATUS_LABEL = {code: label for code, label, _c in STATUS_BUCKETS}

# Legend shown in the title bar — one row per distinct color.
LEGEND = [
    ("In Effect",              "#2E7D32"),
    ("Signed / Passed Leg.",   "#1B5E83"),
    ("Introduced / Committee", "#6A4C93"),
    ("Vetoed / Killed",        "#999999"),
    ("Election / Vote",        "#8B6914"),
]

# Backwards-compatible alias used by a couple of older render paths.
EVENT_COLORS = STATUS_COLOR

# CRE subject tags (source of truth: etl-base/etl/legislation/cre_keywords.yml)
CRE_SUBJECTS = [
    "zoning",
    "land_use",
    "property_tax",
    "rent_control",
    "eviction",
    "habitability",
    "adu",
    "short_term_rental",
    "eminent_domain",
    "tif",
    "opportunity_zone",
    "historic_preservation",
    "impact_fee",
    "affordable_housing",
    "building_code",
    "permitting",
    "mortgage",
    "foreclosure",
    "hoa",
    "insurance",
    "transfer_tax",
]
