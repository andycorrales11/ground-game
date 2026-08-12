/*
  The one place that knows what a position looks like.

  Every class is written out in full rather than composed at runtime: Tailwind
  finds classes by scanning source text, so a template like `text-${pos}`
  produces nothing at all. If you add a position, add its literal classes here.
*/

export interface PositionStyle {
  /** Colour for the rail down the left edge of a board row. Pairs with border-l-[3px]. */
  bar: string;
  /** The position label itself, on the dark ground. */
  text: string;
  /** A filter chip in its selected state: the hue as ground, pitch as text. */
  chip: string;
}

const STYLES: Record<string, PositionStyle> = {
  QB: { bar: 'border-l-qb', text: 'text-qb', chip: 'bg-qb text-pitch' },
  RB: { bar: 'border-l-rb', text: 'text-rb', chip: 'bg-rb text-pitch' },
  WR: { bar: 'border-l-wr', text: 'text-wr', chip: 'bg-wr text-pitch' },
  TE: { bar: 'border-l-te', text: 'text-te', chip: 'bg-te text-pitch' },
  K: { bar: 'border-l-k', text: 'text-k', chip: 'bg-k text-pitch' },
  DEF: { bar: 'border-l-def', text: 'text-def', chip: 'bg-def text-pitch' },
};

/*
  Steel, the same as DEF. An unknown position is nearly always a roster slot the
  board does not project (FLEX, BN), and rendering it in a live position's hue
  would be a lie -- the whole palette rests on hue meaning position.
*/
const UNKNOWN: PositionStyle = {
  bar: 'border-l-def',
  text: 'text-def',
  chip: 'bg-def text-pitch',
};

export function positionStyle(pos: string | null | undefined): PositionStyle {
  if (!pos) return UNKNOWN;
  return STYLES[pos.toUpperCase()] ?? UNKNOWN;
}

/*
  What the board can be filtered to. FLEX is not a position -- the backend
  expands it to RB/WR/TE -- but it is how you actually think mid-draft, so it
  sits inline with the rest.
*/
export const BOARD_FILTERS = ['ALL', 'QB', 'RB', 'WR', 'TE', 'FLEX', 'K', 'DEF'] as const;
export type BoardFilter = (typeof BOARD_FILTERS)[number];

/** Real positions, in depth-chart order, for anything that reports per position. */
export const POSITIONS = ['QB', 'RB', 'WR', 'TE', 'K', 'DEF'] as const;

export const SORT_OPTIONS = [
  { value: 'ADP', label: 'ADP', hint: 'Where the field is taking them' },
  { value: 'PTS', label: 'Proj', hint: 'Projected total points for the season' },
  { value: 'VORP', label: 'VORP', hint: 'Points above replacement' },
  { value: 'VONA', label: 'VONA', hint: 'What waiting costs you' },
] as const;
