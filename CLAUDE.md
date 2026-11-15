# CLAUDE.md — ASTRA engineering guide

ASTRA (Autonomous Scientific Terrain Research & Analysis) ranks Earth locations by
their measured similarity to selected Moon and Mars regions. It is a scientific
research tool: every number shown must trace back to a real dataset, a documented
literature reference, or a documented deterministic calculation.

Read this file before starting work. Update the progress tracker when a task is done.

## Architecture

```text
frontend/ (static, served by FastAPI at /)
  index.html, css/style.css, js/{api,app,views/*}.js   Vanilla JS SPA, hash router,
                                                      Leaflet map, Chart.js charts
backend/
  main.py            FastAPI app, router registration, startup (schema + seed + ingest)
  config.py          Environment-backed settings (.env)
  database/          SQLAlchemy engine/session, models, schema versioning
  data/              Site catalog + vocabularies, NASA POWER client, DEM readers
                     (NASADEM/Copernicus via Planetary Computer, LOLA, MOLA via PDS
                     HTTP range requests), acquisition CLI, ingestion into Measurements
  science/           Deterministic science: terrain metrics, feature registry,
                     normalization, similarity scoring, uncertainty, explanations,
                     mission weight profiles, environment limitations
  services/          Discovery runs, comparisons (glue between DB and science)
  api/               FastAPI routers + Pydantic schemas
  agents/            One tool-calling research agent (LLM optional) + validated tools
  reports/           ReportLab PDF generation
datasets/{earth,moon,mars}/   Acquired real data subsets + provenance JSON sidecars
tests/               pytest: science unit tests, ingestion tests, API tests
```

Data flow: `acquire` (network, run once) → `datasets/` files with provenance →
`ingest` (offline, on startup) → `measurements` table → `discovery` (pure Python
scoring) → results/reports → frontend + agent.

## Technology stack

- Backend: Python 3.12+ (developed on 3.14), FastAPI, SQLAlchemy 2, SQLite, Pydantic 2, Uvicorn
- Science: NumPy, Pandas, Rasterio, Shapely (GeoPandas intentionally not used: no vector
  workloads need it)
- Reports: ReportLab
- Frontend: HTML, CSS, vanilla JS, Leaflet 1.9.4, Chart.js 4.4.1 (CDN, pinned)
- AI: one agent; provider set by `LLM_PROVIDER` env var; deterministic fallback when unset
- Local venv: `.venv/` (created with `python -m venv .venv`); run tests with
  `.venv/Scripts/python.exe -m pytest -q`, app with `.venv/Scripts/python.exe -m backend.main`

## Coding rules

- Modular code; keep frontend/back-end responsibilities separate.
- No secrets in code. All configuration via environment (`.env`, documented in `.env.example`).
- Every external HTTP call has a timeout and error handling; validate responses.
- Cache external API responses (POWER) in SQLite.
- Tests for scientific calculations and API routes; never claim a test passed unless run.
- Don't rewrite completed files without reason; don't leave fake buttons or TODO core features.
- Match existing style: module docstrings, type hints, small functions.

## Scientific integrity rules

1. Never fabricate measurements, datasets, endpoints or citations.
2. Every measurement stores: value, unit, source dataset, method, retrieval time,
   uncertainty (or null if unquantified), and `source_type`
   (`measured_dataset` | `derived` | `literature_reference` | `curated_classification` |
   `physical_constraint`).
3. Missing data is never treated as a match. Missing features are excluded from the
   score and reported via `coverage` and missing-data score bounds.
4. Similarity = 100 × Σ(w_f · s_f) / Σ(w_f) over valid features only. Continuous s_f is a
   Gaussian kernel with documented scale and optional log transform; categorical s_f is
   the Jaccard index of curated tags.
5. Terrain metrics are compared only on a common 500 m analysis grid over a 30 km window
   (documented resampling). Absolute elevation is never compared across bodies (datums differ).
6. Earth thermal values (NASA POWER skin temperature, MERRA-2 based) are compared with
   literature surface temperatures for targets; this approximate equivalence is documented.
7. The LLM never produces measurements or scores. Agent answers cite tool outputs.
8. Always communicate that Earth cannot reproduce lunar/Martian gravity, vacuum or
   atmosphere, radiation environment, or regolith chemistry.
9. Sample/illustrative data, if ever used, must carry `is_sample=True` and be labelled in UI.

## Roadmap and progress tracker

Status: [x] done · [~] partial · [ ] not started

Phase 0 — Foundation
- [x] T01 Inspect repository and environment
- [x] T02 Project structure, scaffold, README, requirements (pre-existing)
- [x] T03 FastAPI app, settings, health endpoint (pre-existing)
- [x] T04 SQLite engine/session, models, schema init, DB health

Phase 1 — Scientific data foundation
- [x] T05 Site catalog (Earth candidates, Moon/Mars targets) with metadata
- [x] T06 NASA POWER daily client (validation, timeout, cache, provenance)
- [x] T07 Earth elevation subsets (NASADEM; Copernicus GLO-30 fallback >60°N/<56°S)
- [x] T08 Lunar LOLA subsets (LDEM_64 cylindrical; LDEM_75S_240M south polar)
- [x] T09 Martian MOLA subsets (MEGDR 128 ppd tiles)
- [x] T10 Measurement ingestion (validation, units, timestamps, provenance, missing data)

Phase 2 — Analysis engine
- [x] T11 Slope, roughness (TRI), relief, steep-slope fraction
- [x] T12 Feature normalization and missing-data handling
- [x] T13 Deterministic similarity scoring with mission weight profiles
- [x] T14 Coverage, uncertainty bounds, dimension scores, mismatch explanations
- [x] T15 Scientific tests + assumptions/limitations doc

Phase 3 — Backend + agent
- [x] T16 Missions and locations APIs
- [x] T17 Discovery run + ranked results APIs
- [x] T18 Research agent with validated tool calling
- [x] T19 Agent connected to real datasets and deterministic functions
- [x] T20 Comparison and report endpoints

Phase 4 — Frontend
- [x] T21 App shell and navigation
- [x] T22 Mission selection/configuration
- [x] T23 Leaflet discovery map
- [x] T24 Ranked list + location detail
- [x] T25 Comparison charts + evidence panels
- [x] T26 AI research interface
- [x] T27 Report viewing and PDF export

Phase 5 — Integration and delivery
- [x] T28 End-to-end integration test
- [x] T29 Validate lunar and Martian workflows
- [x] T30 Bug fixing, provenance, missing-data, API errors
- [~] T31 Production configuration done (Dockerfile, .env.example); NOT built/deployed:
      Docker not installed locally and no deployment target/credentials provided.
      DEPLOYED on Vercel: https://nasa-astra.vercel.app (project nasa-astra, GitHub
      Piyush5321/Astra main auto-deploys). Verified live: pages, API, discovery, agent,
      PDF, live NASA POWER. Without DATABASE_URL (Neon) each instance has its own /tmp
      SQLite, so runs can be missing across instances - connect Neon for persistence.
- [x] T32 README, architecture docs, acknowledgments, demo script, screenshots

## Session log / next action

- 2026-11-15: Inspected repo. Verified network access to NASA POWER, Planetary Computer
  (NASADEM, Copernicus GLO-30), PDS Geosciences (LOLA, MOLA; HTTP Range supported).
  Next action: T04.
- 2026-11-15: Phases 0-3 complete (46 tests passing). Real data acquired for all 14 sites.
  Agent uses anthropic SDK (claude-opus-5-5, fallbacks=default); deterministic fallback.
  Next action: T21 frontend shell.
- 2026-11-15: Phases 4-5 complete. Frontend verified in headless Chrome (desktop + 390 px
  iframe). Fixed during integration: POWER irradiance units (AG = MJ/m2/day), CARTO tiles
  needing a key (switched to NASA GIBS), K-difference shown as Celsius, agent site matching
  on generic words ("crater"), agent using run weights. 46 tests pass.
  Remaining / next actions:
  - Deploy when a target + credentials exist (Dockerfile untested).
  - Exercise the Claude agent with a real key (only mocked tests so far).
  - Curate more target thermal references (Jezero, Meridiani, Aristarchus, south pole).
  - Optional: user-defined candidate locations (POST /api/locations + live acquisition).
- 2026-11-15: Vercel deployment fixes: .gitignore 'data/' excluded backend/data (anchored
  to /data/); rasterio needs libexpat (absent on Vercel) -> runtime reads checksummed .npz
  copies, rasterio moved to requirements-dev; Vercel passes rewritten path /api/index ->
  rewrite carries ?__path= which api/index.py restores. Frontend/PDF now served as whole
  bodies (a suspected streaming bug turned out to be a curl measurement artefact; the
  change is harmless and kept).
