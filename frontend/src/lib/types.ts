// The shapes the backend returns. Simulation and live are two parallel route
// families over the same engine, so they return the same draft state and share
// every type here.

export type DraftMode = 'simulation' | 'live';

export interface Player {
  normalized_name: string;
  display_name: string;
  pos: string;
  team: string | null;
  bye: number | null;
  /** Average draft position. Lower is earlier. Null when the player has no ADP row. */
  ADP: number | null;
  /**
   * Projected total fantasy points for the season, in this league's scoring.
   *
   * The backend copies it here from a format-specific column, so the room never
   * has to know whether the session is PPR, half-PPR or standard. Null means
   * nobody projected them -- the same players who carry a null VORP.
   */
  PTS: number | null;
  /**
   * Points above the replacement-level player at this position. Null means no
   * projection at all -- it does not mean replacement level, which is 0.
   */
  VORP: number | null;
  /** Value over next available: what taking someone else at this position costs. */
  VONA: number | null;
  // The big board also carries format-specific columns (e.g. fantasy_points_ppr).
  [key: string]: string | number | null | undefined;
}

export interface RosterSlot {
  slot: string;
  player: string | null;
  pos: string | null;
  bye: number | null;
}

export interface OnClockTeam {
  type: string;
  roster_id?: string;
  team_index?: number;
}

export interface DraftState {
  session_id: string;
  current_pick_num: number;
  is_user_turn: boolean;
  /** Null once the draft is over: nobody is on the clock. */
  on_clock_team: OnClockTeam | null;
  available_players: Player[];
  drafted_players_count: number;
  total_picks: number;
  user_roster: RosterSlot[];
  /** { week: [player, ...] } for weeks that sideline two or more of your players. */
  bye_conflicts: Record<string, string[]>;
  status: string;
  /*
    League size and length. Optional because older backends do not send them,
    and the only thing that needs them -- the round number on the rail -- is
    omitted rather than guessed when they are absent. total_picks is their
    product, so neither can be recovered from it alone.
  */
  teams?: number;
  rounds?: number;
}

export interface LivePick {
  pick_number: number;
  roster_id: string;
  player_name: string;
  position: string;
}
