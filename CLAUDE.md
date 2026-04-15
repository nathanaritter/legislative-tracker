# Legislative Tracker

Internal Dash app for tracking CRE-relevant legislation across Milestone's target markets. Mirrors analytics-workbench / contract-tracker conventions.

## Architecture

**Data flow**: LegiScan/LegiStar APIs → `ingest/` connectors (raw JSON → Azure Blob, normalized rows → CSV) → `etl-base/processed/market/legislation/` → CSV→Parquet push → this app reads parquet.

**Three tables under `../etl-base/processed/market/legislation/`**:
1. `bills.csv` — one row per bill; free text + AI fields (reference table, mirrors `processed/geography/areas.csv` pattern)
2. `bill_events.csv` — long-format event log (fits `etl/shared/schema.py` standard)
3. `metrics.csv` — long-format aggregates exposed to analytics-workbench via `catalog.csv`

**Storage discipline**: raw per-bill JSON from LegiScan/LegiStar lives **only** in Azure Blob `stdp58902/etl/legislation/raw/...`. Never write per-bill files to the repo tree or anywhere under OneDrive — previous LegiScan bulk-dump runs have created millions of files and strained the sync.

## Key files

- `app.py` — Dash entry, mirrors `analytics-workbench/app.py`
- `config.py` — Azure toggle, paths, brand tokens
- `components/layout.py` — topnav (56px) + sidebar (320px) + main area
- `components/sidebar.py` — state → counties → cities filter cascade
- `components/timeline.py` — Plotly horizontal Gantt
- `components/detail_modal.py` — AI summary + risk gauge + sponsors + text download
- `callbacks/filters.py` — cascading geography/status/subject filters
- `callbacks/timeline.py` — render timeline from filtered bills + events
- `callbacks/detail.py` — click → modal
- `loaders/bills.py` — read `bills.parquet` + `bill_events.parquet` from local or `az://`
- `services/storage.py` — signed blob URL for bill text PDFs
- `ingest/legiscan/client.py` — LegiScan API, direct-to-blob raw writes
- `ingest/legistar/` — abstract base + per-jurisdiction registry

## Design tokens (shared with analytics-workbench, contract-tracker)

- Brand: `#074070` / Light: `#B6D6EF` / Accent: `#589BD5`
- Sidebar 320px, Nav 56px, System fonts 13px
- Bootstrap Icons 1.11.3

## Azure

- Storage account: `stdp58902`, container `etl` (prefix `legislation/` for this app)
- Key Vault: `kv-data-registry-dev` (`LEGISCAN-API-KEY` secret)
- Container Registry: `acrdataplatdevdcbe93ee.azurecr.io`
- Resource group: `rg-data-platform`
- Container App: `ca-legislative-tracker`

## Running locally

```bash
pip install -r requirements.txt
cp .env.example .env   # USE_AZURE=false reads from ../etl-base/parquet/
python app.py          # http://localhost:8050
```
