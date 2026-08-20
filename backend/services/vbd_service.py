import numpy as np
import pandas as pd
from dataclasses import dataclass

from backend import config
from backend import league
from backend.services import data_service, projection_service
from backend import utils
import logging
from .draft import Draft, Team
from .simulation_service import simulate_cpu_pick

# Setup logging
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')

def _position_adjustment(position: str, position_slots: list) -> float:
    """
    The tuning multiplier applied to a position's VORP column, for this lineup.

    `config.POSITION_ADJUSTMENT` dampens QB to 0.8. That is a one-quarterback
    league constant: there, replacement level sits at QB12-ish, where the drop-off
    behind it is shallow enough that raw VORP overstates what an elite quarterback
    is actually worth to a lineup that starts exactly one.

    A superflex league inverts the premise. Replacement level moves to roughly
    QB24, the position becomes the scarcest thing on the board, and the dampener
    would be shaving 20% off the column precisely where it is telling the truth --
    which is the single most reliable way to lose a superflex draft. The slot
    already says the league is different; nothing else has to be configured.
    """
    if position == 'QB' and 'SFLEX' in position_slots:
        return 1.0
    return config.POSITION_ADJUSTMENT.get(position, 1.0)


def calculate_vorp(
    df: pd.DataFrame, 
    position: str, 
    teams: int = config.DEFAULT_TEAMS, 
    format: str = config.DEFAULT_DRAFT_FORMAT,
    roster_config = config.DEFAULT_ROSTER_POS
) -> pd.DataFrame:
    """
    Calculates Value Over Replacement Player (VORP) for a given position and merges it back.

    Args:
        df: DataFrame containing player stats for ALL positions.
        position: The position to calculate VORP for (e.g., 'QB', 'RB').
        teams: The number of teams in the league.
        format: The scoring format (e.g., 'STD', 'PPR').
        roster_config: A list representing the league's roster construction.

    Returns:
        The original DataFrame with a 'VORP' column updated for the specified position.
    """
    if format not in utils.SCORING_FORMATS:
        raise ValueError(f"Unsupported format: {format}")

    points_column = utils.points_column(format)
    if points_column not in df.columns:
        raise KeyError(f"Points column '{points_column}' not found in DataFrame.")

    # Ensure VORP column exists. It starts as NaN, not 0.0: 0 means "exactly
    # replacement level", which is a real and fairly good player, so using it for
    # "no value computed" floats every unknown above everyone below replacement.
    if 'VORP' not in df.columns:
        df['VORP'] = float('nan')

    # Replacement level is how deep the league starts at this position. Flex and
    # superflex slots are charged fractionally across the positions eligible for
    # them; league.replacement_rank owns that split so a superflex league moves
    # QB replacement level without this function knowing what superflex is.
    replacement_level = league.replacement_rank(position, teams, list(roster_config))

    # Sort players by fantasy points for the specified position
    df_pos = df[df['pos'] == position].copy()
    df_pos.sort_values(by=points_column, ascending=False, inplace=True)

    # Find the replacement player. Players with no projection are excluded from the
    # ranking first -- a NaN landing on the replacement index would otherwise make
    # every VORP at the position NaN.
    ranked = df_pos[df_pos[points_column].notna()]
    if len(ranked) > replacement_level:
        replacement_value = ranked.iloc[replacement_level][points_column]
    else:
        replacement_value = 0 # No replacement player found, so VORP is just their score

    # Calculate VORP for the position, applying the positional adjustment. A player
    # with no projection keeps NaN: they are unranked, not replacement level.
    # _json_safe_records turns it into null at the edge, every sort here uses the
    # default na_position='last', and the CPU ranks with na_option='bottom'.
    adjustment_factor = _position_adjustment(position, list(roster_config))
    df_pos['VORP_pos'] = (df_pos[points_column] - replacement_value) * adjustment_factor

    # Update the main DataFrame's VORP column for the specific position
    df.loc[df_pos.index, 'VORP'] = df_pos['VORP_pos']
    
    return df


# How many forward simulations to average when estimating what survives to the
# user's next turn. CPU picks are randomized, so a single run is noisy; each extra
# run costs one more pass of picks_to_simulate CPU picks.
VONA_SIMULATION_RUNS = 5


def simulate_to_next_turn(
    draft_obj: Draft,
    teams_list: list[Team],
    picks_to_simulate: int,
    current_pick: int,
    pick_owners: list[int] | None = None,
) -> pd.DataFrame:
    """
    Plays out the CPU picks between now and the user's next turn.

    Returns the pool that survives. The caller's Draft and Teams are left untouched.

    `pick_owners` is the actual sequence of teams picking, which the caller knows
    and this cannot derive: a pick may have been traded, and a pick already spent
    on a keeper is not made at all. Without it the order falls back to snake
    arithmetic, which is right for any league that has neither.
    """
    draft_sim = Draft(
        draft_obj.players.copy(), draft_obj.format, draft_obj.teams,
        draft_obj.rounds, draft_obj.roster, draft_obj.order,
    )
    draft_sim.drafted_players = draft_obj.drafted_players.copy()
    # Team.copy() carries the picks already made. Building these with
    # Team(roster=t.roster.copy()) only copied the slot *names*, so the simulated
    # opponents started every run with empty rosters and drafted as if it were
    # round one.
    teams_sim = [t.copy() for t in teams_list]

    teams = draft_obj.teams
    draft_order = draft_obj.order

    for i in range(picks_to_simulate):
        if pick_owners is not None:
            team_index = pick_owners[i]
        else:
            pick_num = current_pick + i + 1
            current_round = (pick_num - 1) // teams + 1

            if draft_order == 'snake' and current_round % 2 == 0:
                team_index = teams - ((pick_num - 1) % teams) - 1
            else:
                team_index = (pick_num - 1) % teams

        available_for_cpu = draft_sim.get_available_players()
        if available_for_cpu.empty:
            break

        # VORP is read off the board rather than recomputed here.
        #
        # This loop used to call calculate_vorp for QB/RB/WR/TE against the
        # *available* pool, which quietly meant the simulated opponents valued
        # players on a different basis than the board does: calculate_vorp takes
        # the Nth best row of whatever frame it is given, so replacement level
        # drifted down to worse players as the pool drained, inflating everyone's
        # VORP relative to the static, full-pool figure the user sees.
        #
        # Replacement level is a property of the league's starting requirements,
        # not of who is left, so the board's figure is the right one and the
        # opponents should share it. Dropping the recompute also removes four
        # full passes over the pool per simulated pick, in the hottest loop in
        # the app.
        cpu_team = teams_sim[team_index]
        cpu_pick_name = utils.normalize_name(
            simulate_cpu_pick(available_for_cpu, cpu_team, draft_sim.rounds)
        )
        pos = draft_sim.draft_player(cpu_pick_name)
        if pos:
            cpu_team.add_player(cpu_pick_name, pos)

    return draft_sim.get_available_players()


@dataclass(frozen=True)
class WaitingCost:
    """
    What the forward simulations say about waiting, per player.

    Both are keyed by display name, which is the form the board and the session
    already pass around.
    """

    # Expected points lost by not taking this player now: how far he is above the
    # man you would settle for, weighted by how likely you are to lose him.
    cost: dict[str, float]
    # Probability, in [0, 1], that he is gone before your next turn.
    gone: dict[str, float]


def calculate_vona_board(
    available_players: pd.DataFrame,
    draft_obj: Draft,
    teams_list: list[Team],
    picks_to_simulate: int,
    current_pick: int,
    runs: int = VONA_SIMULATION_RUNS,
    pick_owners: list[int] | None = None,
) -> WaitingCost:
    """
    What waiting costs you, per player, from one shared set of forward simulations.

        cost = P(he is gone by your next turn) x (his points - the next man down's)

    Both halves come out of the same simulations, and both vary per player. That
    is the whole point of the current formulation, because the previous one did
    neither.

    **What this replaced, and why.** VONA used to be
    `max(0, points - best surviving points at that position)`. The subtracted
    term was a single number per position, so within a position the column was
    `points - constant` -- a rank-preserving shift of a column already on the
    board, carrying no information the projection did not. Worse, the clamp
    erased almost all of it: measured on a real 12-team board it produced **7
    non-zero values out of 681 players**, with QB and TE routinely all zero. Its
    entire information content was four numbers, presented as a per-player
    column.

    The fix is to compare a player against the man you would actually settle for
    -- the best survivor at his position ranked *below* him -- rather than
    against the best survivor outright. Against the best outright, every player
    who is not the top of his position scores negative and clamps to zero. The
    next man down is always worse than him, so the gap is a real drop-off and
    the column stays alive all the way down the board.

    Multiplying by the chance he is actually gone is what makes it a decision
    rather than a description: a stud with a cliff behind him who will certainly
    be taken scores high, and the same stud in a flat tier, or one nobody else
    wants yet, scores low. Both are the right answer to "should I take him now?"

    Returns a WaitingCost. `cost` is non-negative by construction -- there is no
    clamp doing the work, the two factors simply cannot be negative.
    """
    points_col = utils.points_column(draft_obj.format)

    names = list(available_players['display_name']) if not available_players.empty else []
    if not names:
        return WaitingCost({}, {})

    # No picks in between means nothing comes off the board, so waiting is free
    # and nobody can be taken ahead of you.
    if picks_to_simulate <= 0:
        return WaitingCost({name: 0.0 for name in names}, {name: 0.0 for name in names})

    candidates = available_players[['display_name', 'normalized_name', 'pos', points_col]]
    points = pd.to_numeric(candidates[points_col], errors='coerce').to_numpy(dtype=float)
    positions = candidates['pos'].to_numpy()
    projected = ~np.isnan(points)

    total = len(candidates)
    survived = np.zeros(total, dtype=float)
    next_down_sum = np.zeros(total, dtype=float)
    next_down_runs = np.zeros(total, dtype=float)
    completed = 0

    for _ in range(max(1, runs)):
        survivors = simulate_to_next_turn(
            draft_obj, teams_list, picks_to_simulate, current_pick, pick_owners
        )
        if survivors.empty:
            continue
        completed += 1

        survived += candidates['normalized_name'].isin(
            set(survivors['normalized_name'])
        ).to_numpy(dtype=float)

        for pos, group in survivors.groupby('pos'):
            # Survivors at this position, ascending, so the best one below a
            # given projection is the neighbour to the left of it.
            surviving_points = np.sort(
                pd.to_numeric(group[points_col], errors='coerce').dropna().to_numpy(dtype=float)
            )
            if surviving_points.size == 0:
                continue

            at_pos = np.flatnonzero((positions == pos) & projected)
            if at_pos.size == 0:
                continue

            # side='left' puts the insertion point before any survivor equal to
            # the candidate, so a player is never compared against himself or
            # against someone tied with him.
            index = np.searchsorted(surviving_points, points[at_pos], side='left')
            has_one_below = index > 0
            below = surviving_points[np.clip(index - 1, 0, None)]

            found = at_pos[has_one_below]
            next_down_sum[found] += below[has_one_below]
            next_down_runs[found] += 1.0

    if completed == 0:
        return WaitingCost({name: 0.0 for name in names}, {name: 0.0 for name in names})

    gone = 1.0 - (survived / completed)

    # A player with no projection (kickers, defenses, the unprojected tail) has no
    # measurable drop-off behind him, and neither does one whose position is so
    # thin that nothing below him survives. Both score 0 rather than a number
    # invented to fill the column.
    measurable = next_down_runs > 0
    drop = np.zeros(total, dtype=float)
    np.divide(next_down_sum, next_down_runs, out=drop, where=measurable)
    drop = np.where(measurable, np.maximum(points - drop, 0.0), 0.0)

    cost = gone * drop

    return WaitingCost(
        cost={name: float(value) for name, value in zip(names, cost)},
        gone={name: float(value) for name, value in zip(names, gone)},
    )


# The board's ADP column when the lineup starts two quarterbacks. Written by
# backend/ingest/ingest_to_db.py; see the ingest notes in CLAUDE.md for why it is
# a column of its own rather than a fourth scoring format.
SUPERFLEX_ADP_COLUMN = 'superflex_adp'


def _superflex_adp(base_df: pd.DataFrame, format_adp: pd.Series) -> pd.Series:
    """
    ADP for a superflex lineup: the superflex column where it exists, the format
    column where it does not.

    The export covers the top 270 players, which leaves kickers, defenses and the
    deep pool on the format column. That mixes two scales, and the mixing is
    deliberate -- an earlier version rescaled the uncovered players onto the
    superflex scale by measuring the drift between the two columns, and it was
    wrong for a specific reason worth writing down.

    **The superflex export lists no kickers and no defenses at all.** So the drift
    measured across covered players partly reflects those ~35 slots being absent
    from that list, which pulls everyone else's superflex number down relative to
    their format number. Applying that drift to a kicker corrects him with a
    figure derived from his own absence. On the real 2026 board it read as +14 at
    ADP 110 and -3 at ADP 160, a pattern with no physical meaning behind it.

    Left alone, the seam costs very little. A kicker or defense is drafted on
    roster-slot timing rather than on scarcity -- you take one in the last rounds
    whatever the format -- so their format ADP is already about the right absolute
    pick, and `simulation_service._apply_late_round_penalty` overrides it by a
    factor of 50 regardless. Everyone else uncovered sits past ADP 270, which is
    beyond the end of a 20-round draft in a 12-team league.

    A player with no ADP in either column keeps NaN and goes on sorting last.
    """
    superflex = pd.to_numeric(base_df[SUPERFLEX_ADP_COLUMN], errors='coerce')
    return superflex.where(superflex.notna(), pd.to_numeric(format_adp, errors='coerce'))


def _apply_engine_projections(
    board: pd.DataFrame, points_col: str, scoring: league.ScoringSettings
) -> pd.DataFrame:
    """
    Overwrites stored projections with ones computed for this league's scoring.

    The board is a **hybrid**, and deliberately so. The projection engine models
    quarterbacks, running backs, receivers and tight ends -- 441 players -- and
    nothing else. Kickers, defenses, and the couple of hundred deep-pool skill
    players it does not list keep the stored per-format projection they have
    always had.

    That seam is visible if you go looking: a fourth-string receiver's points do
    not move when you change the scoring, because his number came from Sleeper.
    It is the right trade anyway. Everyone affected sits far below replacement
    level, where VORP is negative and the ordering barely matters, and the
    alternative -- dropping them -- would empty the back half of a 20-round
    board and put every kicker back at an unprojected NaN.

    Players the engine covers but the board does not are already gone by this
    point; `projected_points` drops them only after projecting them, so their
    share weights still hold their teammates' shares down.
    """
    if 'sleeper_id' not in board.columns:
        logging.warning(
            "Board has no sleeper_id column; keeping stored projections. "
            "Engine projections join on it."
        )
        return board

    try:
        points = projection_service.projected_points(scoring)
    except Exception as error:  # noqa: BLE001 -- never take the draft down over this
        logging.warning("Could not compute engine projections (%s). Keeping stored ones.", error)
        return board

    if points.empty:
        logging.info(
            "No active projection set; the board is using stored %s projections.", points_col
        )
        return board

    computed = board['sleeper_id'].map(points)
    board[points_col] = computed.where(computed.notna(), board[points_col])

    logging.info(
        "Projected %d of %d players from league scoring; %d kept stored projections.",
        int(computed.notna().sum()), len(board), int(computed.isna().sum()),
    )
    return board


def create_vbd_big_board(
    season: int = 2024,
    format: str = config.DEFAULT_DRAFT_FORMAT,
    teams: int = config.DEFAULT_TEAMS,
    scoring: league.ScoringSettings | None = None,
    roster: league.RosterSettings | None = None,
) -> pd.DataFrame:
    """
    Creates a VORP-based "big board" for all positions, incorporating ADP data.

    `format` still selects the ADP column -- there is no way to derive where the
    field drafts a player from a scoring table -- but it no longer decides what a
    player is worth. `scoring` does, and defaults to the format's preset so a
    caller that passes neither gets exactly the old behaviour.
    """
    if roster is not None:
        # One source of truth for the league size. A roster that disagrees with
        # the `teams` argument is the roster's to win: it is the more specific
        # thing the caller passed.
        teams = roster.teams
    roster_positions = (roster.position_slots() if roster else config.DEFAULT_ROSTER_POS)
    scoring = scoring if scoring is not None else league.ScoringSettings.for_format(format)

    # 1. Load player data from the database
    base_df = data_service.load_player_data()
    if base_df is None or base_df.empty:
        logging.error("Could not load player data, cannot create big board.")
        return pd.DataFrame()

    # Ensure base columns exist
    if 'normalized_name' not in base_df.columns and 'display_name' in base_df.columns:
        base_df['normalized_name'] = base_df['display_name'].apply(utils.normalize_name)

    # Map format to database column names
    adp_col_map = {'STD': 'std_adp', 'PPR': 'ppr_adp', 'HalfPPR': 'half_ppr_adp'}
    proj_col_map = {'STD': 'std_proj_pts', 'PPR': 'ppr_proj_pts', 'HalfPPR': 'half_ppr_proj_pts'}

    adp_column = adp_col_map.get(format)
    proj_column = proj_col_map.get(format)

    # Rename the format-specific ADP column to a generic 'ADP'
    if adp_column and adp_column in base_df.columns:
        base_df.rename(columns={adp_column: 'ADP'}, inplace=True)
    else:
        logging.warning(f"ADP column for format '{format}' not found. ADP values will be missing.")
        base_df['ADP'] = None

    # A superflex lineup drafts off a different board, and this is the only place
    # that difference enters: ADP is 90% of the CPU's draft score, so it is what
    # makes simulated opponents take quarterbacks like a superflex league instead
    # of leaving them for round 10.
    if roster is not None and roster.superflex:
        if SUPERFLEX_ADP_COLUMN in base_df.columns:
            covered = int(
                pd.to_numeric(base_df[SUPERFLEX_ADP_COLUMN], errors='coerce').notna().sum()
            )
            base_df['ADP'] = _superflex_adp(base_df, base_df['ADP'])
            logging.info(
                "Superflex lineup: %d player(s) on superflex ADP, %d left on %s "
                "(kickers, defenses and the deep pool the export omits).",
                covered, int(base_df['ADP'].notna().sum()) - covered, adp_column,
            )
        else:
            logging.warning(
                "The lineup has a superflex slot but the players table has no '%s' "
                "column, so the board is using %s ADP -- quarterbacks will look far "
                "cheaper than they are. Re-run: python -m backend.ingest.ingest_to_db",
                SUPERFLEX_ADP_COLUMN, format,
            )

    # Rename the format-specific projection column to the generic 'fantasy_points' name expected by VORP calculation
    fantasy_points_col = utils.points_column(format)
    if proj_column and proj_column in base_df.columns:
        base_df.rename(columns={proj_column: fantasy_points_col}, inplace=True)
    else:
        logging.warning(f"Projection column for format '{format}' not found. Fantasy points will be missing.")
        base_df[fantasy_points_col] = 0.0

    # Replace the stored projection with one computed for this league, wherever
    # the engine covers the player.
    base_df = _apply_engine_projections(base_df, fantasy_points_col, scoring)

    # 4. Calculate VORP for all positions
    final_df = base_df.copy()
    for position in base_df['pos'].unique():
        if position in config.VORP_POSITIONS:
            final_df = calculate_vorp(final_df, position, teams, format, roster_positions)

    # Sort the final big board by VORP
    final_df.sort_values(by='VORP', ascending=False, inplace=True)
    
    return final_df