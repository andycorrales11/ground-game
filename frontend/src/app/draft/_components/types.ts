// Shared between the simulation and live draft rooms, which return the same
// draft-state shape from two parallel route families.

export interface Player {
  normalized_name: string;
  display_name: string;
  pos: string;
  team: string | null;
  bye: number | null;
  ADP: number | null;
  VORP: number | null;
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

export interface DraftState {
  session_id: string;
  current_pick_num: number;
  is_user_turn: boolean;
  on_clock_team: { type: string; roster_id?: string; team_index?: number };
  available_players: Player[];
  drafted_players_count: number;
  total_picks: number;
  user_roster: RosterSlot[];
  // { week: [player, ...] } for weeks that sideline two or more of your players.
  bye_conflicts: Record<string, string[]>;
  status: string;
}
