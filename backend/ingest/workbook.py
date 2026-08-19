"""
Reads the projection workbook's *inputs* -- and nothing else.

The workbook (`data/2026-FFB-Projections-0817.xlsx`) is a five-stage spreadsheet
pipeline, but only the first stage is data. Everything downstream -- stat lines,
scoring, ranks, VORP -- is arithmetic this codebase does itself, against the
league's own settings rather than the workbook's. So this module reads the
yellow cells and stops.

**Never read a computed cell here.** The temptation is real, because the cached
values are right there and the formulas are tedious. But a cached value is frozen
at the scoring settings the workbook was last saved with, which is the one thing
the whole engine exists to make configurable. The cached values have exactly one
legitimate use, in `cached_values()`: they are the oracle the parity tests check
the engine against.

Layout notes that are load-bearing (spec §3):

- Position blocks sit at **fixed rows** with blank spacers between them. Do not
  scan for position labels -- empty slots and the spacer rows make that fragile.
- The editable share columns (AD/AE/AF) are **relative weights, not percentages**.
  Normalizing them is the engine's job, not the parser's.
- `AG` is a raw per-reception touchdown rate despite the neighbouring `AB`
  column rendering it as a share. Carry it through raw.
"""
from pathlib import Path
from typing import Dict, List, Tuple

from backend.services.projection_engine import (
    PlayerRates,
    ProjectionInputs,
    TeamVolume,
)

# The 32 team tabs, in workbook order. Listed rather than derived by excluding
# known non-team sheets: a new presentation tab should not silently become a
# team, and a renamed team tab should fail loudly.
TEAM_TABS: Tuple[str, ...] = (
    'ARI', 'ATL', 'BAL', 'BUF', 'CAR', 'CHI', 'CIN', 'CLE',
    'DAL', 'DEN', 'DET', 'GB', 'HOU', 'IND', 'JAX', 'KC',
    'LV', 'LAC', 'LAR', 'MIA', 'MIN', 'NE', 'NO', 'NYG',
    'NYJ', 'PHI', 'PIT', 'SF', 'SEA', 'TB', 'TEN', 'WSH',
)

# Inclusive row spans per position. The gaps (rows 5, 12, 21) are spacers.
POSITION_BLOCKS: Dict[str, Tuple[int, int]] = {
    'QB': (2, 4),
    'RB': (6, 11),
    'WR': (13, 20),
    'TE': (22, 25),
}

# Team volume inputs.
CELL_PLAYS = 'D29'
CELL_PASS_PCT = 'E29'
CELL_RUSH_YPC = 'G29'

# Player input columns.
COL_NAME = 'A'
COL_POS = 'B'
COL_COMP_PCT = 'R'
COL_YDS_PER_COMP = 'S'
COL_PASS_TD_PCT = 'T'
COL_INT_PCT = 'U'
COL_RUSH_YPC = 'V'
COL_RUSH_TD_RATE = 'X'
COL_CATCH_RATE = 'Y'
COL_YDS_PER_REC = 'Z'
COL_W_PASS = 'AD'
COL_W_RUSH = 'AE'
COL_W_TGT = 'AF'
COL_REC_TD_RATE = 'AG'


def _number(cell_value) -> float:
    """
    A cell as a float, treating blank and non-numeric as zero.

    Non-numeric is folded in with blank deliberately: the input cells are
    hand-maintained, and a stray label in a rate column should degrade that one
    player rather than fail the whole import. The unmatched/zero-rate reports
    are what surface it.
    """
    if cell_value is None:
        return 0.0
    if isinstance(cell_value, (int, float)):
        return float(cell_value)
    try:
        return float(str(cell_value).strip())
    except ValueError:
        return 0.0


def _text(cell_value) -> str:
    return '' if cell_value is None else str(cell_value).strip()


def _parse_team_tab(sheet, team: str) -> Tuple[TeamVolume, List[PlayerRates]]:
    volume = TeamVolume(
        team=team,
        plays=_number(sheet[CELL_PLAYS].value),
        pass_pct=_number(sheet[CELL_PASS_PCT].value),
        rush_ypc=_number(sheet[CELL_RUSH_YPC].value),
    )

    players: List[PlayerRates] = []
    for pos, (first, last) in POSITION_BLOCKS.items():
        for row in range(first, last + 1):
            name = _text(sheet[f'{COL_NAME}{row}'].value)
            if not name:
                continue  # An unfilled depth-chart slot.

            def val(column: str) -> float:
                return _number(sheet[f'{column}{row}'].value)

            players.append(PlayerRates(
                team=team,
                # The team-tab row doubles as the within-team key. It is stable
                # for as long as the workbook's fixed blocks are, and nothing
                # downstream does arithmetic with it.
                key=row,
                name=name,
                # The position column is authoritative where it is filled in, but
                # the row block is what the formulas key off, so it wins.
                pos=pos,
                w_pass=val(COL_W_PASS),
                w_rush=val(COL_W_RUSH),
                w_tgt=val(COL_W_TGT),
                comp_pct=val(COL_COMP_PCT),
                yds_per_comp=val(COL_YDS_PER_COMP),
                pass_td_pct=val(COL_PASS_TD_PCT),
                int_pct=val(COL_INT_PCT),
                rush_ypc=val(COL_RUSH_YPC),
                rush_td_rate=val(COL_RUSH_TD_RATE),
                catch_rate=val(COL_CATCH_RATE),
                yds_per_rec=val(COL_YDS_PER_REC),
                rec_td_rate=val(COL_REC_TD_RATE),
            ))

    return volume, players


def load_workbook_projections(path: str | Path) -> ProjectionInputs:
    """
    Parses every team tab into engine inputs.

    Opened with `data_only=False`, which is the guard that matters: a formula
    cell comes back as its formula string, and `_number` reads that as zero. If
    somebody points this at a computed column by mistake, they get zeros and a
    loud downstream report -- not plausible-looking frozen numbers.
    """
    import openpyxl

    workbook = openpyxl.load_workbook(path, data_only=False, read_only=True)
    try:
        missing = [tab for tab in TEAM_TABS if tab not in workbook.sheetnames]
        if missing:
            raise ValueError(
                f"Workbook is missing team tab(s): {', '.join(missing)}. "
                f"Expected all {len(TEAM_TABS)} NFL teams."
            )

        volumes: Dict[str, TeamVolume] = {}
        players: List[PlayerRates] = []
        for team in TEAM_TABS:
            volume, team_players = _parse_team_tab(workbook[team], team)
            volumes[team] = volume
            players.extend(team_players)
    finally:
        workbook.close()

    return ProjectionInputs(volumes=volumes, players=players)
