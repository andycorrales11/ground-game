# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Ground Game is a fantasy football draft assistant built on a Value-Based Drafting (VBD) model. A FastAPI backend computes player valuations and manages draft state; a Next.js frontend provides the draft room UI. It runs in two modes against the same engine: **simulation** (CPU-controlled opponents) and **live assistant** (polls a real Sleeper draft).

## Commands

All Python commands must be run **from the repository root** — imports are absolute (`from backend...`) and `config.py` resolves data paths from `Path.cwd()`.

**Use the project venv interpreter, not bare `python`.** The `python` on PATH is 3.9, and the codebase uses PEP 604 unions (`str | None`) throughout, which raise `TypeError` on 3.9. The venv at `.venv/` is Python 3.12.10 and holds all dependencies.

```powershell
.\.venv\Scripts\python.exe -m <module>    # Windows
.venv/bin/python -m <module>              # POSIX
```

```bash
# Backend API (frontend hardcodes http://localhost:8000)
uvicorn backend.main:app --reload --port 8000

# Frontend
cd frontend && npm run dev      # dev server on :3000
cd frontend && npm run build
cd frontend && npm run lint
cd frontend && npm test

# Single frontend test
cd frontend && npm test -- page.test.tsx
cd frontend && npm test -- -t "renders the draft page"

# Backend tests (pytest is NOT in requirements.txt — pip install pytest)
pytest backend/tests/
pytest backend/tests/simulation_service_test.py
pytest backend/tests/simulation_service_test.py::test_calculate_draft_score

# Data ingestion (see Data Pipeline below)
python -m backend.ingest.ingest_to_db    # CSV -> Postgres; what the app actually reads
python -m backend.ingest.ingest_all      # API/parquet pipeline -> data/
python -m backend.print_db_data          # inspect what's in the players table
```

`backend/tests/vorp_test.py` is **not** a standard pytest test — it is a print-based script (`python -m backend.tests.vorp_test`) that hits the live database rather than fixtures, so exclude it: `pytest backend/tests/ --ignore=backend/tests/vorp_test.py`. Everything else runs without a database.

### Environment

`.env` at repo root (gitignored) supplies `DB_HOST`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`. It also contains `GEMINI_API_KEY`, which is currently unused by any code.

Database schema is in `schema.sql` (single `players` table). `data/` is gitignored — the FantasyPros ADP CSVs and Athletic projection CSVs must be downloaded manually and are not in the repo.

### Upstream source status (verified 2026-08-06)

- **Sleeper players API** (`ingest_players.py`, `sleeper_service.py`) — live and unchanged. 12,210 players, all expected fields present.
- **`nfl.import_ids()`** (`ingest_to_db.py`, supplies the `sleeper_id` primary key) — live and current, already includes the 2026 draft class.
- **`nfl.import_seasonal_data()`** (`ingest_stats.py`) — **broken for seasons after 2024**; returns HTTP 404. `nfl_data_py` is no longer maintained against current data paths (successor package: `nflreadpy`). This only affects the parquet pipeline, which has no runtime consumer, so it does **not** block the app.
- **FantasyPros ADP CSVs** — columns `Rank, Player, Team, Bye, POS, AVG`; `AVG` is renamed to `*_adp` during ingest. Shape still matches the parser. 2026 files must be downloaded manually.
- **Athletic projection CSVs** — tab-separated despite the `.csv` extension; columns `RK, Player, TM, BYE, FPS`. Shape still matches. 2026 files must be downloaded manually.

## Architecture

### Request flow

`backend/main.py` (FastAPI routes) → `DraftManagerService` (session state) → `Draft`/`Team` (domain models) + `vbd_service` (valuation) + `simulation_service` (CPU behavior).

`DraftManagerService` holds all sessions in a **class-level in-memory dict** (`_active_draft_sessions`), keyed by a UUID. State does not survive a restart and does not work across multiple worker processes.

### The two-track endpoint surface

`main.py` exposes parallel `/draft/simulation/*` and `/draft/helper/*` route families. The `*_helper` methods on `DraftManagerService` are **thin passthroughs to the simulation methods** — identical behavior, except `process_auto_pick_helper`, which is the only genuinely distinct one. Mode is actually determined by whether `draft_id` is set in the session, not by which route was called.

The frontend mirrors this split, and each mode stays on its own routes end to end:

| | Entry page | Start endpoint | Draft room | Polls |
|---|---|---|---|---|
| Simulation | `/draft` | `/draft/simulation/start` | `/draft/simulation/[session_id]` | nothing; you drive it with "Simulate Next Pick" |
| Live | `/draft/helper` | `/draft/helper/start` | `/draft/helper/[session_id]` | `/draft/helper/{id}/poll-live` every 8s |

The live room must not offer a CPU-pick button — `process_cpu_pick` returns an error for any session with a `draft_id`.

### Simulation vs. live mode

The branch point is `session_state["draft_id"]`:

- **Simulation** — `get_user_picks()` precomputes the user's pick numbers; team-on-clock is derived from snake math (`current_round % 2 == 0` reverses the order); CPU picks are generated by `simulate_cpu_pick`.
- **Live** — settings come from `sleeper_service.get_draft_settings(draft_id)`; a `picks_order` list and `slot_to_roster_id` map are precomputed at init; `poll_live_draft_updates` fetches picks from Sleeper and replays them into the local `Draft`. `teams_list` rosters are **not** populated in live mode (Sleeper owns rosters), so positional-need logic is inert there.

The same snake-order calculation is reimplemented in four places (`draft_manager_service` ×3, `vbd_service.calculate_vona`). Changing draft-order logic means changing all of them.

### Valuation: VORP and VONA

`backend/services/vbd_service.py`:

- **VORP** — points above the replacement-level player at that position. Replacement level is `(starters × teams) + (flex × teams × 0.5)` for RB/WR (hardcoded 50/50 flex split), `starters × teams` otherwise. Result is scaled by `config.POSITION_ADJUSTMENT` (QB is dampened to 0.8). Only computed for QB/RB/WR/TE — K and DEF always have VORP 0.
- **VONA** — value over next available. Runs a *real forward simulation* of every CPU pick until the user's next turn, then compares the candidate against the best remaining player at the same position.

  **The forward simulation does not depend on the candidate** — the candidate only enters in the final subtraction. So `calculate_vona_board` runs the simulation once (`VONA_SIMULATION_RUNS = 5`, averaged to damp the CPU randomness) and scores the whole board against that one expected outcome. Do not reintroduce a per-candidate simulation: it is ~11× slower *and* makes the column internally incomparable, because each player would be scored against a different random future.

  `_ensure_vona` caches the result against `(current_pick_num, len(drafted_players))`. `get_current_draft_state` is hit on every filter change and every live-draft poll, so recomputing unconditionally is what made the UI feel frozen.

`create_vbd_big_board()` loads the whole `players` table and renames the format-specific columns (`ppr_adp` → `ADP`, `ppr_proj_pts` → `fantasy_points_ppr`) into the generic names the rest of the pipeline expects.

### Scoring formats are baked into the schema

Formats are **columns**, not rows: `std_adp`/`half_ppr_adp`/`ppr_adp` and `std_proj_pts`/`half_ppr_proj_pts`/`ppr_proj_pts`. `calculate_vorp` hard-rejects anything outside `['STD', 'PPR', 'HalfPPR']`, and `config.DEFAULT_ROSTER` is a module-level constant rather than per-league config. Supporting superflex, TE premium, 2QB, IDP, or custom scoring requires changing the schema, not just adding a branch.

**Never derive a format string or column name inline.** `'HalfPPR'.lower()` is `'halfppr'`, but every column uses `half_ppr` — that one-character gap made half-PPR raise a `KeyError` on every draft, because `create_vbd_big_board` bridged it and `calculate_vorp` didn't. Both now go through `backend/utils.py`:

- `normalize_scoring_format(x)` → canonical `'STD' | 'PPR' | 'HalfPPR'`, accepting Sleeper's `half_ppr`, the setup form's `HALF_PPR`, and anything else that strips to the same letters. Do **not** `.upper()` the result; `HalfPPR` is mixed-case by design.
- `points_column(x)` → the big board's projection column, e.g. `fantasy_points_half_ppr`.

### CPU draft behavior

`backend/services/simulation_service.py` scores players on a **lower-is-better** scale:

- `simulate_cpu_pick` — blends VORP rank and ADP rank 10/90, applies a ×5.0 penalty for a 3rd QB and a ×0.70 bonus for unfilled starting slots, then samples from the top 10 with a fixed probability vector (60% top choice) so drafts aren't deterministic.
- `simulate_user_auto_pick` — VONA/VORP/ADP weighted 50/20/30, picks the single best score with no randomness.

### Name matching

`sleeper_id` is the primary key, and **projections now join on it** rather than on a name — that path has no name matching at all. What still goes through names:

- Resolving a FantasyPros ADP row to a Sleeper id, via `nfl.import_ids()` plus the manual `NAME_MAP` for players nflverse and FantasyPros spell differently (e.g. `"Deebo Samuel Sr."`).
- `create_vbd_big_board` joining on `normalized_name` (`backend/utils.py` — strips suffixes, lowercases, underscores).

**Store ids in Sleeper's own form** (`"4034"`, and the bare abbreviation for defenses). `nfl.import_ids()` returns them numerically, so a plain `str()` yields `"4034.0"` and silently fails to match the feed — `canonical_sleeper_id()` strips that. Live-draft pick matching tries both forms, so it tolerates either.

**Inconsistency to watch:** `Team.add_player()` is called with *normalized* names in `draft_manager_service`, but `Team.count_players_at_position()` looks players up by `display_name`. The lookup never matches, so the CPU's QB-count penalty does not currently fire.

### Data pipeline

Two pipelines exist and only one feeds the app:

1. **`ingest/ingest_to_db.py`** — **ADP** from `data/fantasy_pros_adp/*.csv`, **projections** from Sleeper's live feed, joined on `sleeper_id`, then `TRUNCATE` + bulk-`COPY` into Postgres. **This is what the running app reads.**
2. **`ingest/ingest_all.py`** (`ingest_players` → `ingest_adp` → `ingest_stats`) — pulls from the Sleeper players API and nflverse via `nfl_data_py`, writing parquet into `data/`. No runtime code path reads these parquet files; `data_service.load_player_data()` reads only from Postgres.

**Projections come from `ingest/sleeper_projections.py`**, not from CSVs. One request to `api.sleeper.com/projections/nfl/{season}` returns all three scoring formats keyed by Sleeper id, so projections join on the primary key rather than on a name. It also covers K and DEF, which the Athletic CSVs never did.

The Athletic CSV path still exists behind `GG_PROJECTIONS=csv`, purely so the two boards can be diffed. It joins by `display_name` and is the older, more fragile route.

```powershell
# Default: FantasyPros ADP + Sleeper projections
.\.venv\Scripts\python.exe -m backend.ingest.ingest_to_db

# A past season, or the CSV projection source
$env:GG_SEASON = "2025"; .\.venv\Scripts\python.exe -m backend.ingest.ingest_to_db
$env:GG_PROJECTIONS = "csv"; .\.venv\Scripts\python.exe -m backend.ingest.ingest_to_db
```

**FantasyPros changes its export layout between seasons.** `ADP_FILENAME_PATTERNS` holds the known filename conventions and `_normalize_adp_frame` reduces either column layout to `Player/POS/Team/AVG`. The 2026 export folds team and bye into the player cell (`"Jahmyr Gibbs   DET (6)"`), omits `Team` and `Bye`, and carries a per-site column set that differs between the three files. Expect to add a pattern rather than rewrite the loader.

Season values are still hardcoded in the unused parquet pipeline: `ingest_stats.py` defaults to `season=2024` and `ingest_adp.py` hardcodes `FantasyPros_2025_*`.

### Ingest invariants

These were all bugs at one point; keep them true.

- **NaN must never reach the database.** `prepare_data` ends with `.astype(object).where(pd.notna(...), None)` so missing values land as SQL `NULL`. Written as raw pandas NaN through `COPY`, they become the literal string `'nan'` in varchar columns and IEEE `NaN` in `double precision` columns — and `IS NULL` matches neither, so the data looks clean while being garbage.
- **`pos` and `team` are coalesced across all three ADP files**, then fall back to the position/team encoded in the projection filenames. Reading them from the STD file alone leaves ~20% of the board positionless.
- **Defenses need special handling.** FantasyPros lists them by full team name with `Team` set to the literal `"DST"`, and `nfl.import_ids()` doesn't cover them. `DEFENSE_TEAM_ABBR` maps the name to the abbreviation, which becomes both `team` and `sleeper_id` (Sleeper keys defenses by abbreviation). Position is normalized `DST` → `DEF` to match `config.DEFAULT_ROSTER`.
- **API responses must be NaN-free.** `_json_safe_records` in `draft_manager_service` converts NaN to `None` before serialization; `json.dumps` emits a bare `NaN` literal that `JSON.parse` rejects. K and DEF rows have no projections, so filtering to those positions is what triggers it.

## Known stale code

- **`backend/services/auth_service.py` is empty.**
- `backend/tests/vorp_test.py` filters on a `position` column, but the database and all runtime code use `pos`. (The same bug in `simulation_service_test.py` has been fixed.)
