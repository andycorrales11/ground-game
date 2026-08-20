import pandas as pd
import numpy as np
from .draft import Team

# Kickers and defenses are the last two picks of a normal draft. Their ADP sits
# around 120-200, which by the middle rounds is better than anything left on the
# board, and they carry real VORP now -- so without an explicit brake the CPU
# takes a defense in round 8, well before its bench is filled.
LATE_ROUND_POSITIONS = ('K', 'DEF')

# Rounds at the end of the draft where an unfilled K/DEF slot becomes the priority.
LATE_ROUND_GRACE = 2
LATE_ROUND_BONUS = 0.15

# Multiplier on the (lower-is-better) score before then. This has to be large: a
# defense is usually the best ADP left on the board by the middle rounds, so its
# raw score is near 1.0, and the CPU samples from the top 10. A x12 penalty only
# moved it to about rank 8 -- still inside the sampling window, which is how
# defenses were still going in round 10 of 15.
LATE_ROUND_PENALTY = 50.0

# The exception: within ELITE_WINDOW rounds of the end, the single best remaining
# kicker and defense are only lightly penalised. This is the elite defense that
# comes off the board a round or two early.
ELITE_WINDOW = 4
ELITE_PENALTY = 8.0

# Roster has one K slot and one DEF slot, so a second of either is a wasted pick.
DUPLICATE_PENALTY = 100.0


def _apply_late_round_penalty(players: pd.DataFrame, score_column: str,
                              team: Team, rounds_remaining: int) -> None:
    """
    Keeps kickers and defenses on the board until the bench is filled, then makes
    sure the slot actually gets filled before the draft ends.

    Modifies `players` in place. Scores are lower-is-better, so a multiplier above
    1.0 is a penalty and below 1.0 is a bonus.

    Three regimes per position:
      already rostered  -- effectively unpickable, there is only one slot
      final few rounds  -- strongly preferred, so teams do not finish without one
      everything before -- heavily penalised, except the best one left once the
                           draft is close to the end
    """
    for pos in LATE_ROUND_POSITIONS:
        at_pos = players['pos'] == pos
        if not at_pos.any():
            continue

        if team.count_players_at_position(pos) >= 1:
            players.loc[at_pos, score_column] *= DUPLICATE_PENALTY
        elif rounds_remaining <= LATE_ROUND_GRACE:
            players.loc[at_pos, score_column] *= LATE_ROUND_BONUS
        else:
            players.loc[at_pos, score_column] *= LATE_ROUND_PENALTY
            if rounds_remaining <= ELITE_WINDOW:
                ranked = players.loc[at_pos & players['VORP'].notna(), 'VORP']
                if not ranked.empty:
                    # Swap the flat penalty for the lighter one on the best available.
                    players.loc[ranked.idxmax(), score_column] *= ELITE_PENALTY / LATE_ROUND_PENALTY


# A team may roster one more quarterback than it can start before the CPU treats
# it as hoarding. Read off the lineup rather than fixed at 2: a superflex league
# starts two, so the old constant made a *starting* lineup look like a third-QB
# stockpile and taught every CPU team to leave the format's scarcest position on
# the board.
QB_SURPLUS_ALLOWED = 1


def _qb_saturation_point(team: Team) -> int:
    """
    The number of quarterbacks at which one more becomes a wasted pick.

    Slots the team was built with are the source: QB slots plus superflex slots,
    since a superflex is a quarterback slot in all but name, plus one backup. A
    default lineup gives 1 + 0 + 1 = 2, exactly the constant this replaced.
    """
    startable = sum(
        1 for slot in team.roster
        if slot.startswith('QB') or slot.startswith('SFLEX')
    )
    return startable + QB_SURPLUS_ALLOWED


def calculate_positional_scarcity(players: pd.DataFrame) -> dict:
    """
    Calculates the VORP drop-off for each position to determine scarcity.
    """
    scarcity = {}
    for pos in ['QB', 'RB', 'WR', 'TE']:
        # Unprojected players carry NaN VORP; drop them rather than let one land on
        # iloc[1] and make the whole gap NaN, which then loses every max() it enters.
        ranked = players.loc[players['pos'] == pos, 'VORP'].dropna().sort_values(ascending=False)
        scarcity[pos] = float(ranked.iloc[0] - ranked.iloc[1]) if len(ranked) > 1 else 0.0
    return scarcity

def calculate_draft_score(players: pd.DataFrame) -> pd.DataFrame:
    """
    Calculates a blended draft score based on VORP and ADP ranks.
    """
    players = players.copy()
    # Create ranks for VORP (higher is better)
    players['vorp_rank'] = players['VORP'].rank(ascending=False, na_option='bottom')
    
    # Create ranks for ADP (lower is better)
    if 'ADP' in players.columns:
        # Fill missing ADP with a high number to rank them lower
        players['adp_rank'] = players['ADP'].fillna(999).rank(ascending=True, na_option='bottom')
        # Blend the two ranks, giving more weight to ADP
        players['draft_score'] = (0.10 * players['vorp_rank']) + (0.90 * players['adp_rank'])
    else:
        # If no ADP data, the score is just the VORP rank
        players['draft_score'] = players['vorp_rank']
        
    return players

def simulate_cpu_pick(available_players: pd.DataFrame, team: Team, total_rounds: int,
                      picks_remaining: int | None = None) -> str:
    """
    Simulates a CPU pick using a balanced approach of Best Player Available (BPA),
    positional need, and positional scarcity.

    `picks_remaining` is how many picks this team still has to make. It defaults
    to `total_rounds - team.picks_made`, which is only the same thing in a league
    where nobody trades picks: a manager who traded three away has twelve in a
    fifteen-round draft, and on the derived count never reaches the last-rounds
    window that makes a team fill its kicker and defense slots.
    """
    # 1. Calculate draft_score for all available players to establish a BPA baseline.
    players = calculate_draft_score(available_players)

    # 2. Apply penalties and bonuses
    # QB Penalty: once the team can neither start nor bench another, hold off.
    if team.count_players_at_position('QB') >= _qb_saturation_point(team):
        players.loc[players['pos'] == 'QB', 'draft_score'] *= 5.0 # Heavy penalty

    # Starter Bonus: Prioritize filling starting spots
    starting_needs = team.get_starting_positional_needs()
    if starting_needs:
        needed_indices = players[players['pos'].isin(starting_needs)].index
        players.loc[needed_indices, 'draft_score'] *= 0.70 # Significant bonus

    # K and DEF are starting slots too, so the bonus above actively pulls them
    # forward. Hold them back until the bench is nearly full.
    if picks_remaining is None:
        picks_remaining = total_rounds - team.picks_made
    _apply_late_round_penalty(players, 'draft_score', team, picks_remaining)

    # Scarcity Bonus
    scarcity = calculate_positional_scarcity(players)
    if scarcity:
        scarcest_position = max(scarcity, key=scarcity.get)
        top_player_at_scarcest = players[players['pos'] == scarcest_position].sort_values(by='ADP', ascending=False).head(1)
        if not top_player_at_scarcest.empty:
            player_index = top_player_at_scarcest.index[0]
            players.loc[player_index, 'draft_score'] -= 10

    # 3. Make the pick based on the adjusted score.
    top_10 = players.sort_values(by='draft_score', ascending=True).head(10)
    
    if top_10.empty:
        return "No players available"
        
    choices = top_10['display_name'].tolist()
    
    probabilities = [0.60, 0.20, 0.10, 0.05, 0.02, 0.01, 0.005, 0.005, 0.005, 0.005]
    
    if len(choices) < len(probabilities):
        probabilities = probabilities[:len(choices)]
        prob_sum = sum(probabilities)
        if prob_sum > 0:
            probabilities = [p / prob_sum for p in probabilities]
        else:
            probabilities = [1 / len(choices)] * len(choices)

    return np.random.choice(choices, p=probabilities)

def simulate_user_auto_pick(available_players: pd.DataFrame, team: Team, total_rounds: int,
                            picks_remaining: int | None = None) -> str:
    """
    Simulates a user's auto-pick using a VONA-enhanced hybrid score.

    `picks_remaining` as in `simulate_cpu_pick`: a team that traded picks away has
    fewer than the round count implies.
    """
    if available_players.empty:
        return "No players available"

    # 1. Create ranks for VONA, VORP, and ADP
    players = available_players.copy()
    players['vona_rank'] = players['VONA'].rank(ascending=False, na_option='bottom')
    players['vorp_rank'] = players['VORP'].rank(ascending=False, na_option='bottom')
    players['adp_rank'] = players['ADP'].fillna(999).rank(ascending=True, na_option='bottom')

    # 2. Calculate the hybrid auto_pick_score
    players['auto_pick_score'] = (0.5 * players['vona_rank']) + \
                                 (0.2 * players['vorp_rank']) + \
                                 (0.3 * players['adp_rank'])

    # 3. Apply penalties and bonuses
    # QB Penalty
    if team.count_players_at_position('QB') >= _qb_saturation_point(team):
        players.loc[players['pos'] == 'QB', 'auto_pick_score'] *= 5.0

    # Starter Bonus
    starting_needs = team.get_starting_positional_needs()
    if starting_needs:
        needed_indices = players[players['pos'].isin(starting_needs)].index
        players.loc[needed_indices, 'auto_pick_score'] *= 0.75

    if picks_remaining is None:
        picks_remaining = total_rounds - team.picks_made
    _apply_late_round_penalty(players, 'auto_pick_score', team, picks_remaining)

    # Scarcity Bonus
    scarcity = calculate_positional_scarcity(players)
    if scarcity:
        scarcest_position = max(scarcity, key=scarcity.get)
        top_player_at_scarcest = players[players['pos'] == scarcest_position].sort_values(by='VORP', ascending=False).head(1)
        if not top_player_at_scarcest.empty:
            player_index = top_player_at_scarcest.index[0]
            players.loc[player_index, 'auto_pick_score'] -= 5

    # 4. Make the pick based on the best (lowest) auto_pick_score
    best_pick = players.sort_values(by='auto_pick_score', ascending=True).iloc[0]
    
    return best_pick['display_name']