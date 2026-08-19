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

# Single frontend test. Note two files are named page.test.tsx (the two entry
# pages), so a bare filename matches both -- pass a path to isolate one.
cd frontend && npm test -- src/app/draft/__tests__/page.test.tsx
cd frontend && npm test -- -t "renders the draft page"

# Backend tests (pytest is NOT in requirements.txt — pip install pytest)
pytest backend/tests/
pytest backend/tests/simulation_service_test.py
pytest backend/tests/simulation_service_test.py::test_calculate_draft_score

# Data ingestion (see Data Pipeline below). Order matters: projections resolve
# against the players table, so ingest_to_db has to run first.
python -m backend.ingest.ingest_to_db      # ADP + fallback projections -> players
python -m backend.ingest.ingest_projections  # workbook -> projection_* tables
python -m backend.ingest.ingest_all        # API/parquet pipeline -> data/
python -m backend.print_db_data            # inspect what's in the players table

# Regenerate the engine's golden-master fixture (needs the workbook in data/)
python -m backend.tests.fixtures.generate_workbook_parity
```

`backend/tests/vorp_test.py` is **not** a standard pytest test — it is a print-based script (`python -m backend.tests.vorp_test`) that hits the live database rather than fixtures, so exclude it: `pytest backend/tests/ --ignore=backend/tests/vorp_test.py`. Everything else runs without a database.

### Environment

`.env` at repo root (gitignored) supplies `DB_HOST`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`. It also contains `GEMINI_API_KEY`, which is currently unused by any code.

Database schema is in `schema.sql` (`players`, plus the `projection_*` tables described under Projections below). `data/` is gitignored — the FantasyPros ADP CSVs and the projection workbook must be downloaded manually and are not in the repo.

### Upstream source status (verified 2026-08-06)

- **Sleeper players API** (`ingest_players.py`, `sleeper_service.py`) — live and unchanged. 12,210 players, all expected fields present.
- **`nfl.import_ids()`** (`ingest_to_db.py`, supplies the `sleeper_id` primary key) — live and current, already includes the 2026 draft class.
- **`nfl.import_seasonal_data()`** (`ingest_stats.py`) — **broken for seasons after 2024**; returns HTTP 404. `nfl_data_py` is no longer maintained against current data paths (successor package: `nflreadpy`). This only affects the parquet pipeline, which has no runtime consumer, so it does **not** block the app.
- **FantasyPros ADP CSVs** — columns `Rank, Player, Team, Bye, POS, AVG`; `AVG` is renamed to `*_adp` during ingest. Shape still matches the parser. 2026 files must be downloaded manually.
- **Projection workbook** (`data/2026-FFB-Projections-0817.xlsx`) — the input source for `ingest/workbook.py`. 48 sheets, 32 team tabs, 454 players. Layout verified cell-for-cell against `data/01-cheatsheet-engine-spec.md`. Must be downloaded manually.
- **Athletic projection CSVs** — no longer read by anything. The projection engine supersedes them; `load_projection_data` and the `GG_PROJECTIONS=csv` branch have been deleted.

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

The same snake-order calculation is reimplemented in five places (`draft_manager_service` ×4, `vbd_service.calculate_vona`). Changing draft-order logic means changing all of them.

**Every pick path has to check `_is_complete` first.** It is `current_pick_num >= rounds * teams`, which in live mode is the same bound as `len(picks_order)`. Only live mode used to check anything; simulation was unbounded, so `process_cpu_pick` cycled the team index round the board on the modulo and "Simulate next pick" kept drafting for hundreds of picks past the final round until the player pool ran dry. `get_current_draft_state` returns its **full** payload with `status: "completed"` and a null `on_clock_team` — a bare status, which is what live mode returned, leaves the room with nothing to render at exactly the moment you want to look at the roster you ended up with.

**Roster length follows the round count.** `config.roster_slots(rounds)` is the fixed starting lineup plus exactly enough bench, and `initialize_draft` passes it to both `Draft` and every `Team`. A fixed 18-slot roster meant the default 20-round draft dropped two picks with nowhere to sit (`Team.add_player` still tallies them, so only the panel loses them) and the setup form's 15-round default drew three bench rows nobody could ever fill.

Each board row carries `PTS`, the season projection, copied from the format-specific `fantasy_points_*` column by `get_current_draft_state`. It is a **copy, not a rename** — VORP is derived from that column and the CPU simulation reads it off the same board by its real name. The alias exists because the response never says which scoring format the session is in, so the frontend would otherwise have to guess the column name. Unprojected players keep NaN and reach the client as `null`, on the same rule as VORP.

`get_current_draft_state` also returns `user_roster` and `bye_conflicts`, built by `_roster_and_conflicts`. The user's own `Team` is found by `_user_team`, which is the one place that knows simulation indexes `teams_list` by draft slot while live mode indexes it by roster id.

### Valuation: VORP and VONA

`backend/services/vbd_service.py`:

- **VORP** — points above the replacement-level player at that position. Replacement level comes from `league.replacement_rank(position, teams, position_slots)`: starters plus a fractional charge for each flex and superflex slot, split by `league.FLEX_SHARE` (RB/WR 50/50) and `league.SUPERFLEX_SHARE` (all QB). With the default lineup this is exactly the old `(starters × teams) + (flex × teams × 0.5)`. Result is scaled by `config.POSITION_ADJUSTMENT` (QB is dampened to 0.8; anything absent is 1.0). Computed for every position in `config.VORP_POSITIONS`, which now includes K and DEF — they were excluded only because the Athletic CSVs never projected them.

  The `POSITION_ADJUSTMENT` factor is a tuning constant applied *after* the subtraction, so it rescales a position's whole column rather than shifting its baseline.

  **VORP is static for the whole draft.** It is computed once in `create_vbd_big_board` and never recomputed — a 40-pick run changes 0 of 652 values. That is correct for classic VBD, since replacement level is a property of league structure and not of who is left, but it does mean VORP is a preseason ranking that says nothing new as the draft unfolds. VONA is the column that responds to draft state, and the frontend's tier cliffs (`lib/tiers.ts`) are what read scarcity off VORP gaps.

  **VORP 0 means replacement level, never "no data."** A player with no projection keeps `NaN`, which sorts last everywhere (`sort_values` defaults to `na_position='last'`, the CPU ranks with `na_option='bottom'`, and `_json_safe_records` emits `null`). Filling it with 0.0 instead put 163 players — every K and DEF plus ~78 unprojected skill players — above everyone below replacement level, so sorting the board by VORP after round 8 returned almost nothing but kickers.
- **VONA** — what waiting costs. Runs a *real forward simulation* of every CPU pick until the user's next turn (`VONA_SIMULATION_RUNS = 5`), then:

  ```
  cost = P(gone before your next turn) × (his points − the next man down's)
  ```

  Both factors come out of the same simulations and both vary per player. `calculate_vona_board` returns a `WaitingCost` carrying `cost` (the VONA column) and `gone` (the probability on its own, surfaced as `GONE` on each board row).

  **Do not go back to subtracting the best survivor at the position.** That was the previous formula, and it failed twice over: the subtracted term was one number per position, so within a position the column was `points − constant` — a rank-preserving shift of the projection, carrying nothing the `PTS` column did not already say — and the `max(0, …)` clamp then erased almost all of it. Measured on a real 12-team board: **7 non-zero values out of 681 players**, with QB and TE routinely all zero. Comparing against the *next man down* instead keeps the subtrahend per-player and makes the gap a real drop-off, and multiplying by the risk is what turns a description into a decision — a 336-point QB who is only 40% likely to be taken correctly scores near zero.

  A zero now means "the simulations never took him before your turn", which is the set you do not have to decide about. Expect roughly `picks_to_simulate` players to carry a non-zero cost — not the whole board, and that is correct.

  **The forward simulation does not depend on the candidate**, so it runs a handful of times up front and scores the whole board against one shared set of futures. Do not reintroduce a per-candidate simulation: it is ~11× slower *and* makes the column internally incomparable, because each player would be scored against a different random future.

  **VONA is live on every pick, not only on yours.** The span it simulates is "the pick on the clock through to the user's next turn", and that span is defined whoever is on the clock — off-turn it is simply longer, and the column reads as *who will still be here when I pick*. Simulation mode used to look the pick on the clock up in `user_picks_simulation` and give up when it was not there, leaving `picks_to_simulate` at 0, which `calculate_vona_board` correctly reads as "waiting is free" and answers with a board of exact zeroes; the room had to grey the column out and print an em dash for every pick that was not the user's. Live mode already asked the right question (`next user pick index > current_pick_num`), so the two branches now agree.

  On the user's own turn the span **includes the pick on the clock** — `(next_user_pick - 1) - current_pick_num`. That is deliberate: passing on a player still means spending the pick on somebody else, so one more player leaves the pool. Back-to-back picks at the snake's turn therefore simulate 1 pick, not 0.

  `_ensure_vona` caches the result against `(current_pick_num, len(drafted_players))`. `get_current_draft_state` is hit on every filter change and every live-draft poll, so recomputing unconditionally is what made the UI feel frozen. That cache is what makes computing off-turn affordable: the cost is one pass (~0.84s) per pick, not one per request, and every pick path already recomputes unconditionally after making its pick.

  **`simulate_to_next_turn` reads VORP off the board rather than recomputing it.** It used to call `calculate_vorp` per position against the *available* pool, which meant the simulated opponents valued players on a different basis than the board does — `calculate_vorp` takes the Nth row of whatever frame it is given, so replacement level drifted to worse players as the pool drained. Replacement level is a property of the league's starting requirements, not of who is left. Removing the recompute also cut a VONA pass from 1.22s to 0.84s.

  Cost scales linearly in runs and buys only probability resolution: 5 runs → 0.84s and steps of 0.2; 20 runs → 3.78s and steps of 0.05. Note `runs=VONA_SIMULATION_RUNS` is bound as a **default argument**, so reassigning the module attribute at runtime does nothing — pass the parameter.

  **The simulated opponents must inherit the real rosters** — `simulate_to_next_turn` builds them with `Team.copy()`. It previously used `Team(roster=t.roster.copy())`, and since the constructor takes slot *names*, iterating a roster dict handed it the keys and produced an empty team. Every opponent then drafted as though it were round one, which flattens positional need to a no-op and inflated VONA at whichever position the field had already filled.

`create_vbd_big_board()` loads the whole `players` table and renames the format-specific columns (`ppr_adp` → `ADP`, `ppr_proj_pts` → `fantasy_points_ppr`) into the generic names the rest of the pipeline expects.

### Projections: the engine, and what it does not cover

Projections are **computed at draft time**, not read out of a column. `backend/services/projection_engine.py` takes team volume and per-player share weights and efficiency rates, and scores them against the league's own `ScoringSettings`. This is what makes six-point passing touchdowns, a TE premium, and per-position PPR values expressible at all.

The pipeline is `ingest/workbook.py` (parse inputs) → `projection_players`/`projection_teams` (store) → `services/projection_service.py` (load + score) → `_apply_engine_projections` (overlay onto the board).

**The extractor must never read a computed cell.** `ingest/workbook.py` opens the workbook with `data_only=False`, so a formula cell reads back as its formula string and `_number` turns it into 0 — a loud failure rather than plausible frozen numbers. The one place allowed to read cached values is `tests/fixtures/generate_workbook_parity.py`, where they are the oracle.

**Parity is the gate, at 1e-9.** `tests/projection_engine_test.py` reproduces the workbook's own cached values across 447 players × 12 stat categories. Excel computed those independently, so agreement at 1e-9 is real evidence. If it fails, do not widen the tolerance — a wrong share denominator or a per-attempt/per-completion mixup misses by percent. Two documented exceptions cover the workbook's five hardcoded cells (`ARI!G4`, `NO!L3:O3`); both are workbook defects and both are asserted by shape so they cannot quietly grow.

Three formula asymmetries are load-bearing:

- Pass **yards and touchdowns derive from completions**; interceptions derive from attempts.
- Rush and target shares are scaled ×0.98 (deliberate leakage for unlisted players); **pass share is not**, because every attempt must be thrown by a listed QB.
- The receiving-TD rate is **raw per reception**, not renormalized — so editing one player's does not dilute teammates.

**The board is a hybrid, on purpose.** The engine covers QB/RB/WR/TE only — 441 of 723 board rows. Kickers, defenses, and the deep pool keep the stored `*_proj_pts` from Sleeper. The seam is visible (a fourth-string receiver's points don't move when scoring changes) and is the right trade: everyone affected is far below replacement level, and the alternative empties the back half of a 20-round board and returns every kicker to NaN.

**Unresolved players are stored, not dropped.** 13 workbook players don't match anything on the board. They still go into `projection_players` with a null `sleeper_id`, because share weights are *relative* — dropping them renormalizes their teammates' shares upward and silently changes every projection on that team. `projected_points` drops them only at the very end, after projecting.

Scoring formats are still **columns** for ADP — `std_adp`/`half_ppr_adp`/`ppr_adp` — and always will be: there is no way to derive where the field drafts a player from a scoring table. So a session carries both a `format` (picks the ADP column, seeds the scoring defaults) and a `ScoringSettings` (what actually scores the board). `calculate_vorp` still hard-rejects any format outside `['STD', 'PPR', 'HalfPPR']`.

### League settings

`backend/league.py` holds `ScoringSettings` and `RosterSettings`, both optional on `/draft/*/start` as `scoring` and `roster`. **Unknown keys in either raise rather than being ignored** — a typo in a scoring override would otherwise mis-score an entire draft in silence.

`RosterSettings()` with no arguments reproduces `config.DEFAULT_STARTERS` exactly, which is what keeps every existing draft unchanged; `league_test.py` asserts this directly. Superflex is supported: it adds an `SFLEX` slot, `Team.add_player` fills it with a QB (after `FLEX`, so a running back does not strand the next quarterback), and it doubles QB replacement level.

Three things read the roster and all three must agree: `create_vbd_big_board`, the VONA forward simulation (which recovers the lineup from the `Draft`'s slot names via `league.position_slots_from`), and `Team`. A `Draft` carries slot *names* only, which is why that recovery exists.

The form is `draft/_components/LeagueSettings.tsx`, shared by both entry pages, with the shapes and defaults in `lib/league.ts` mirroring `backend/league.py` field for field.

**Both sections are opt-in, and that is a correctness requirement rather than a tidiness one.** A live draft reads its scoring format from Sleeper; a form that always sent a scoring table would silently override a standard-scoring league with whatever preset it happened to be showing. Off sends nothing at all and lets the backend decide. On sends the **whole object** — never a diff against defaults, which would make `lib/league.ts` and `backend/league.py` have to stay in lockstep to avoid scoring the board on values the form never displayed.

Changing the scoring format re-seeds **only the three reception fields**, because that is the only thing a format decides (`receptionsFor`). A six-point passing touchdown survives switching from PPR to standard. The live page has no scoring select of its own, so `LeagueSettings` renders a "Start from" preset there instead — it seeds the form and says nothing about the Sleeper league, whose format still picks the ADP column.

**Never derive a format string or column name inline.** `'HalfPPR'.lower()` is `'halfppr'`, but every column uses `half_ppr` — that one-character gap made half-PPR raise a `KeyError` on every draft, because `create_vbd_big_board` bridged it and `calculate_vorp` didn't. Both now go through `backend/utils.py`:

- `normalize_scoring_format(x)` → canonical `'STD' | 'PPR' | 'HalfPPR'`, accepting Sleeper's `half_ppr`, the setup form's `HALF_PPR`, and anything else that strips to the same letters. Do **not** `.upper()` the result; `HalfPPR` is mixed-case by design.
- `points_column(x)` → the big board's projection column, e.g. `fantasy_points_half_ppr`.

### CPU draft behavior

`backend/services/simulation_service.py` scores players on a **lower-is-better** scale:

- `simulate_cpu_pick` — blends VORP rank and ADP rank 10/90, applies a ×5.0 penalty for a 3rd QB and a ×0.70 bonus for unfilled starting slots, then samples from the top 10 with a fixed probability vector (60% top choice) so drafts aren't deterministic.

**Kickers and defenses are held back by `_apply_late_round_penalty`.** K/DEF ADP sits around 120–200, which is the best thing left on the board by the middle rounds, and K/DEF are *starting* slots so the ×0.70 need bonus actively pulls them forward. Three regimes, keyed off `total_rounds - team.picks_made`:

| Situation | Multiplier | Effect |
|---|---|---|
| Already have one | `DUPLICATE_PENALTY` 100 | only one slot exists |
| Final `LATE_ROUND_GRACE` (2) rounds | `LATE_ROUND_BONUS` 0.15 | the empty slot becomes the priority |
| Otherwise | `LATE_ROUND_PENALTY` 50 | bench first |
| …but best available, within `ELITE_WINDOW` (4) | `ELITE_PENALTY` 8 | the elite defense that goes early |

**The penalty has to be this large.** A defense with the best remaining ADP scores near 1.0, and the CPU samples from the top *10* — ×12 only moved it to about rank 8, still inside the window, so defenses still went in round 10. And the final-rounds *bonus* is not optional: with a penalty that merely lifted, 40 of 60 teams finished the draft with no kicker at all.

`rounds_remaining` comes from `Team.picks_made`, deliberately — not a fifth copy of the snake-order arithmetic.
- `simulate_user_auto_pick` — VONA/VORP/ADP weighted 50/20/30, picks the single best score with no randomness. It reads a `VONA` column that lives in the session, not on the board, so **every caller must attach it first**; `get_current_draft_state` attaches it to its own copy, and `process_auto_pick_helper` not doing the same is what made `POST /draft/helper/{id}/auto-pick` raise `KeyError: 'VONA'` on every call.

Neither takes the big board any more. They only ever used it to count a team's players by position, which `Team` now tracks itself.

### Name matching

`sleeper_id` is the primary key, and **projections now join on it** rather than on a name — that path has no name matching at all. What still goes through names:

- Resolving a FantasyPros ADP row to a Sleeper id, via `nfl.import_ids()`. `_build_name_index` / `_resolve_sleeper_id` try four keys, most specific first: `(exact name, pos)`, `exact name`, `(normalized name, pos)`, `normalized name`. A key covering two different ids is discarded rather than guessed at.
  - **Position is not optional.** nflverse lists two Lamar Jacksons (Ravens QB, Panthers CB) and two Justin Jeffersons (Vikings WR, 2026 Browns LB). Matching on name alone is a coin flip that silently strips the ADP off a first-round player.
  - **Normalization is what bridges suffixes**, which FantasyPros writes and nflverse mostly does not — `"James Cook III"`, `"Patrick Mahomes II"`, `"Travis Etienne Jr."`. Exact-only matching dropped 86 of 598 ADP rows; the player then reappeared from the projection feed with no ADP at all. Do **not** add suffix variants to `NAME_MAP` — that is what the normalized tier is for. `NAME_MAP` is only for genuinely different spellings (`"Kenny Gainwell"` → `"Kenneth Gainwell"`).
  - `_fill_ids_from_projections` gets a second pass at whatever is left, using Sleeper's own projection feed as the name source. It covers rookies nflverse has not picked up yet, kickers especially.
- `create_vbd_big_board` joining on `normalized_name` (`backend/utils.py` — strips suffixes, lowercases, underscores).
- Resolving a **workbook player to a board player**, in `ingest_projections._resolve`. Three keys, most specific first: `(normalized name, pos, team)`, `(normalized name, pos)`, `normalized name`; ambiguous keys are rejected rather than guessed. 441 of 454 resolve on the strictest key alone.
  - It has **its own `NAME_MAP`, and one entry points the opposite way** to `ingest_to_db`'s: nflverse writes "Kenneth Gainwell" and FantasyPros writes "Kenny", and since the board is built from FantasyPros spellings, the workbook's "Kenneth" has to come back the other direction. Do not merge the two maps.
  - **The 13 that do not resolve are still stored.** See the Projections section — dropping them would renormalize their teammates' shares.

**Store ids in Sleeper's own form** (`"4034"`, and the bare abbreviation for defenses). `nfl.import_ids()` returns them numerically, so a plain `str()` yields `"4034.0"` and silently fails to match the feed — `canonical_sleeper_id()` strips that. Live-draft pick matching tries both forms, so it tolerates either.

**`Team` does not match on names at all.** Callers disagree about which form goes into `Team.roster` — `draft_manager_service` adds normalized names, the VONA simulation used to add display names — so `count_players_at_position` used to look rostered players up in the big board by `display_name` and always return 0, meaning the CPU's 3rd-QB penalty never fired. It now reads a tally that `add_player` maintains from the `pos` it is already given. Keep it that way: the roster's name form is not a contract.

### Data pipeline

Three pipelines exist. Two feed the app, and **they must be run in order** — projections resolve against the board, not the other way round:

1. **`ingest/ingest_to_db.py`** — **ADP** from `data/fantasy_pros_adp/*.csv`, **fallback projections** from Sleeper's live feed, joined on `sleeper_id`, then `TRUNCATE` + bulk-`COPY` into the `players` table. This is the board.
2. **`ingest/ingest_projections.py`** — parses the workbook into `projection_sets`/`projection_teams`/`projection_players`, resolving each player to a `sleeper_id` against the `players` table. These are the *inputs* the engine scores at draft time; nothing here computes a fantasy point.
3. **`ingest/ingest_all.py`** (`ingest_players` → `ingest_adp` → `ingest_stats`) — pulls from the Sleeper players API and nflverse via `nfl_data_py`, writing parquet into `data/`. No runtime code path reads these parquet files; `data_service.load_player_data()` reads only from Postgres.

**The Sleeper feed is now a fallback, not the board's numbers.** One request to `api.sleeper.com/projections/nfl/{season}` returns all three scoring formats keyed by Sleeper id, so it joins on the primary key rather than on a name — and it covers K and DEF, which is exactly the gap the engine leaves.

**Each projection import is a new set, and the previous one stays.** `projection_sets.is_active` (with a partial unique index enforcing one active set) is what the board reads. Re-importing a corrected workbook is non-destructive and leaves last week's numbers available to diff against.

```powershell
# 1. The board: FantasyPros ADP + Sleeper fallback projections
.\.venv\Scripts\python.exe -m backend.ingest.ingest_to_db

# 2. The projection inputs the engine scores
.\.venv\Scripts\python.exe -m backend.ingest.ingest_projections --label "week 1"

# A past season
$env:GG_SEASON = "2025"; .\.venv\Scripts\python.exe -m backend.ingest.ingest_to_db
```

**FantasyPros changes its export layout between seasons.** `ADP_FILENAME_PATTERNS` holds the known filename conventions and `_normalize_adp_frame` reduces either column layout to `Player/POS/Team/AVG`. The 2026 export folds team and bye into the player cell (`"Jahmyr Gibbs   DET (6)"`), omits `Team` and `Bye`, and carries a per-site column set that differs between the three files. Expect to add a pattern rather than rewrite the loader.

Season values are still hardcoded in the unused parquet pipeline: `ingest_stats.py` defaults to `season=2024` and `ingest_adp.py` hardcodes `FantasyPros_2025_*`.

### Ingest invariants

These were all bugs at one point; keep them true.

- **NaN must never reach the database.** `prepare_data` ends with `.astype(object).where(pd.notna(...), None)` so missing values land as SQL `NULL`. Written as raw pandas NaN through `COPY`, they become the literal string `'nan'` in varchar columns and IEEE `NaN` in `double precision` columns — and `IS NULL` matches neither, so the data looks clean while being garbage.
- **`pos`, `team` and `bye` are coalesced across all three ADP files**, then fall back to the position/team encoded in the projection filenames. Reading them from the STD file alone leaves ~20% of the board positionless.
- **One team, one abbreviation.** FantasyPros writes `JAC` for Jacksonville's players; Sleeper and `DEFENSE_TEAM_ABBR` write `JAX`. Left alone that is two franchises, which put 33 teams on a 32-team board and split Jacksonville's bye across both. `TEAM_ABBR_ALIASES` folds the known divergences; `_canonicalize_teams` applies them before anything groups by team.
- **Defenses need special handling.** FantasyPros lists them by full team name with `Team` set to the literal `"DST"`, and `nfl.import_ids()` doesn't cover them. `DEFENSE_TEAM_ABBR` maps the name to the abbreviation, which becomes both `team` and `sleeper_id` (Sleeper keys defenses by abbreviation). Position is normalized `DST` → `DEF` to match `config.DEFAULT_ROSTER`.
- **API responses must be NaN-free.** `_json_safe_records` in `draft_manager_service` converts NaN to `None` before serialization; `json.dumps` emits a bare `NaN` literal that `JSON.parse` rejects. Unprojected players carry NaN ADP *and* NaN VORP, so this is load-bearing on every response.
- **Never `drop_duplicates` on a key column that still holds NaN.** pandas treats every NaN as equal to every other, so it collapses all the unresolved rows into one — which is how a report meant to name the dropped players ended up naming a single arbitrary one. Split the frame, dedupe the identified rows, concat the rest back.
- **`bye` is an `INT` column and must reach `COPY` as one.** `_fill_byes_from_team` casts to `Int64` before the NaN sweep; carried as a float it arrives as `"6.0"`, which Postgres rejects for an integer column.

### Bye weeks

A bye is a property of the NFL **team**, not the player, and that is what makes the coverage work. Both FantasyPros layouts carry it — 2025 as its own `Bye` column, 2026 folded into the player cell (`"Jahmyr Gibbs   DET (6)"`, already captured by `PLAYER_BYE_RE`) — and `_fill_byes_from_team` then dates everyone else from a team-mate. That covers the projection-only deep pool, who arrive from Sleeper with a team but no ADP row, and defenses, whose team abbreviation is their id. The per-team value is the **mode**, so one malformed row cannot redate a whole roster.

652 of 723 players have a bye. The 71 without are exactly the unsigned free agents, who have no team to inherit one from — `Team.bye_conflicts` skips a null bye rather than bucketing them, since grouping them would invent a week where the whole bench disappears.

`Team` records the bye at `add_player` time alongside the position tally, for the same reason: the roster's name form is not a contract, so looking it up afterwards would mean matching on a name. `Draft.player_bye` is what supplies it, and returns `None` for a board with no `bye` column at all — the synthetic test boards predate it.

**Live mode populates the user's team**, which it otherwise does not do (Sleeper owns the rosters). The bye warning is worth more in a real draft than in a simulation, so `poll_live_draft_updates` adds picks whose `roster_id` matches the user's.

## Known stale code

- `ingest/ingest_all.py` and the parquet pipeline it drives have no runtime consumer, and `ingest_stats.py` 404s for any season after 2024. Migrate to `nflreadpy` or delete it.
- `data/projections/athletic_*.csv` are no longer read by anything. The loader that read them has been deleted; the files can go too.
- `backend/services/auth_service.py` was an empty file and has been deleted. Nothing imported it.
