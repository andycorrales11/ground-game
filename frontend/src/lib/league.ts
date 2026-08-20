/*
  What a league pays, and who it starts.

  This mirrors `backend/league.py` field for field. The names are the payload:
  the backend rejects any key it does not recognise rather than ignoring it, so a
  typo here surfaces as a 400 rather than as a draft scored on the wrong rules.

  Both objects are sent **whole or not at all**. There is no diffing against
  defaults, deliberately: a diff would mean these constants have to stay in
  lockstep with the backend's, and a drift would silently score the board with
  values the form never showed. Send everything and the board uses exactly what
  is on screen; send nothing and the backend's own preset applies.
*/

export interface ScoringSettings {
  pass_attempts: number;
  completions: number;
  pass_yards: number;
  pass_tds: number;
  interceptions: number;
  rush_attempts: number;
  rush_yards: number;
  rush_tds: number;
  targets: number;
  receptions_rb: number;
  receptions_wr: number;
  receptions_te: number;
  recv_yards: number;
  recv_tds: number;
}

export interface RosterCounts {
  qb: number;
  rb: number;
  wr: number;
  te: number;
  flex: number;
  superflex: number;
  k: number;
  dst: number;
}

/** The scoring formats, and the only thing that differs between them. */
const PER_CATCH: Record<string, number> = {
  STD: 0,
  HalfPPR: 0.5,
  PPR: 1,
};

/**
 * The reception values for a format.
 *
 * Split out because it is the *only* part of a scoring table a format decides.
 * Changing format re-seeds these three fields and leaves everything else the
 * user has set alone.
 */
export function receptionsFor(format: string): Pick<
  ScoringSettings,
  'receptions_rb' | 'receptions_wr' | 'receptions_te'
> {
  const perCatch = PER_CATCH[format] ?? 0.5;
  return {
    receptions_rb: perCatch,
    receptions_wr: perCatch,
    receptions_te: perCatch,
  };
}

/** The preset for a format. Matches `ScoringSettings.for_format` on the backend. */
export function scoringForFormat(format: string): ScoringSettings {
  return {
    pass_attempts: 0,
    completions: 0,
    pass_yards: 0.04,
    pass_tds: 4,
    interceptions: -2,
    rush_attempts: 0,
    rush_yards: 0.1,
    rush_tds: 6,
    targets: 0,
    recv_yards: 0.1,
    recv_tds: 6,
    ...receptionsFor(format),
  };
}

/** Matches `RosterSettings()` with no arguments -- the lineup the app has always used. */
export const DEFAULT_ROSTER: RosterCounts = {
  qb: 1,
  rb: 2,
  wr: 2,
  te: 1,
  flex: 2,
  superflex: 0,
  k: 1,
  dst: 1,
};

/*
  Named lineups, so a league that is not the default is one click rather than
  eight number fields. These are whole `RosterCounts`, not diffs -- the same rule
  the payload follows, and for the same reason: what is on screen is exactly what
  the board gets built from.

  A superflex lineup with no TE slot is a real format and worth having here,
  because it is the one where getting the lineup wrong is least visible. Nothing
  on screen looks off; the tight ends are just quietly valued against a
  replacement level that does not exist.
*/
export interface RosterPreset {
  label: string;
  hint: string;
  roster: RosterCounts;
}

export const ROSTER_PRESETS: RosterPreset[] = [
  {
    label: 'Standard',
    hint: '1QB · 2RB · 2WR · TE · 2FLEX',
    roster: DEFAULT_ROSTER,
  },
  {
    label: 'Superflex',
    hint: '1QB · 2RB · 2WR · 2FLEX · SF',
    roster: { qb: 1, rb: 2, wr: 2, te: 0, flex: 2, superflex: 1, k: 1, dst: 1 },
  },
];

export interface ScoringField {
  key: keyof ScoringSettings;
  label: string;
}

export interface ScoringGroup {
  title: string;
  fields: ScoringField[];
}

/*
  Grouped the way a league's rules page is, not the way the dataclass is. The
  per-position reception values sit together because seeing them adjacent is the
  point -- a tight-end premium is the one scoring rule most tools cannot express.
*/
export const SCORING_GROUPS: ScoringGroup[] = [
  {
    title: 'Passing',
    fields: [
      { key: 'pass_yards', label: 'Pass yard' },
      { key: 'pass_tds', label: 'Pass TD' },
      { key: 'interceptions', label: 'Interception' },
      { key: 'pass_attempts', label: 'Attempt' },
      { key: 'completions', label: 'Completion' },
    ],
  },
  {
    title: 'Rushing',
    fields: [
      { key: 'rush_yards', label: 'Rush yard' },
      { key: 'rush_tds', label: 'Rush TD' },
      { key: 'rush_attempts', label: 'Carry' },
    ],
  },
  {
    title: 'Receiving',
    fields: [
      { key: 'recv_yards', label: 'Rec yard' },
      { key: 'recv_tds', label: 'Rec TD' },
      { key: 'targets', label: 'Target' },
      { key: 'receptions_rb', label: 'Catch (RB)' },
      { key: 'receptions_wr', label: 'Catch (WR)' },
      { key: 'receptions_te', label: 'Catch (TE)' },
    ],
  },
];

export interface RosterField {
  key: keyof RosterCounts;
  label: string;
  /** Shown under the field. Only where the slot does something non-obvious. */
  hint?: string;
}

export const ROSTER_FIELDS: RosterField[] = [
  { key: 'qb', label: 'QB' },
  { key: 'rb', label: 'RB' },
  { key: 'wr', label: 'WR' },
  { key: 'te', label: 'TE' },
  { key: 'flex', label: 'FLEX', hint: 'RB/WR/TE' },
  { key: 'superflex', label: 'SUPERFLEX', hint: 'QB too' },
  { key: 'k', label: 'K' },
  { key: 'dst', label: 'D/ST' },
];

/** Whether a lineup has any slot at all. The backend rejects an empty one. */
export function hasStartingSlot(roster: RosterCounts): boolean {
  return Object.values(roster).some((count) => count > 0);
}
