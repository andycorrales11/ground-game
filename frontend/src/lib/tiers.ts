import type { Player } from './types';

/*
  Tiers, and the cliffs between them.

  A tier break is a gap in VORP. Points above replacement is the quantity
  tiering is actually about -- it is what the whole valuation model exists to
  produce -- and it already rides on every board row, so nothing extra has to be
  fetched to draw the cliff.
*/

export interface TierInfo {
  /** 1-based, and scoped to the player's own position. RB tier 2, WR tier 2. */
  tier: number;
  /** True when the next player at this position falls into a lower tier. */
  isLastOfTier: boolean;
  /** Points given up by waiting past this player for the next one. Null unless isLastOfTier. */
  dropToNext: number | null;
}

/*
  The threshold is a multiple of the *median* gap at that position -- not the
  mean, and not a standard deviation.

  A position returns as few as half a dozen players on an unfiltered board. At
  that size a single enormous gap drags the mean up past itself, so the gap that
  should define the cliff no longer clears its own bar and the position reports
  one flat tier. The median does not move for it.
*/
const GAP_MULTIPLE = 1.8;

/*
  And a floor, in season-long fantasy points. Without it a genuinely flat
  position splinters into one tier per player: if six receivers sit inside three
  points of each other, the gaps between them are all tiny but some are still
  1.8x the median. Roughly half a point a week is the smallest difference worth
  reorganising a draft board around.
*/
const MIN_GAP = 8;

function median(values: number[]): number {
  if (values.length === 0) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0 ? (sorted[mid - 1] + sorted[mid]) / 2 : sorted[mid];
}

function hasVorp(player: Player): player is Player & { VORP: number } {
  return typeof player.VORP === 'number' && Number.isFinite(player.VORP);
}

/**
 * Assigns every player a tier within their own position, keyed by normalized_name.
 *
 * Players with no projection are absent from the result rather than tiered.
 * A null VORP means no data, not replacement level, and slotting them in at
 * zero would invent a bottom tier out of players nobody has projected.
 */
export function assignTiers(players: Player[]): Map<string, TierInfo> {
  const result = new Map<string, TierInfo>();

  const byPosition = new Map<string, Player[]>();
  for (const player of players) {
    const group = byPosition.get(player.pos);
    if (group) {
      group.push(player);
    } else {
      byPosition.set(player.pos, [player]);
    }
  }

  for (const group of byPosition.values()) {
    const ranked = group.filter(hasVorp).sort((a, b) => b.VORP - a.VORP);
    if (ranked.length === 0) continue;

    const gaps: number[] = [];
    for (let i = 1; i < ranked.length; i += 1) {
      gaps.push(ranked[i - 1].VORP - ranked[i].VORP);
    }

    const threshold = Math.max(median(gaps) * GAP_MULTIPLE, MIN_GAP);

    let tier = 1;
    for (let i = 0; i < ranked.length; i += 1) {
      const gapAfter = i < gaps.length ? gaps[i] : null;
      const breaksAfter = gapAfter !== null && gapAfter >= threshold;

      result.set(ranked[i].normalized_name, {
        tier,
        isLastOfTier: breaksAfter,
        dropToNext: breaksAfter ? gapAfter : null,
      });

      if (breaksAfter) tier += 1;
    }
  }

  return result;
}

/**
 * Whether a cliff can honestly be drawn into this list.
 *
 * Tiers are an ordering on VORP, but the board can be sorted by ADP or VONA
 * instead. Under those the tiers interleave, and a rule reading "tier 2 ends"
 * would sit above a row that is back in tier 1 -- the marker would be a lie
 * about the very thing it exists to point at. Rather than restrict the feature
 * to one sort, check the property the drawing actually depends on: that tiers
 * never go backwards as you read down. Under a VORP sort that always holds.
 */
export function tiersAreInReadingOrder(
  players: Player[],
  tiers: Map<string, TierInfo>,
): boolean {
  let previous = 0;
  for (const player of players) {
    const info = tiers.get(player.normalized_name);
    if (!info) continue;
    if (info.tier < previous) return false;
    previous = info.tier;
  }
  return true;
}

export interface Scarcity {
  pos: string;
  /** How many players are left in the best tier still on the board. */
  remaining: number;
  /** What the drop costs once they are gone. Null when nothing better is known. */
  dropToNext: number | null;
}

/**
 * How thin each position is right now: the size of its best remaining tier.
 *
 * This is the same cliff the board draws as a rule, aggregated for the view
 * where rules cannot be drawn -- an unfiltered board interleaves positions, so
 * a horizontal line across it would separate players who were never competing.
 * Returned sorted by scarcity, because the thinnest position is the decision.
 */
export function scarcityByPosition(
  players: Player[],
  tiers: Map<string, TierInfo>,
): Scarcity[] {
  const byPosition = new Map<string, TierInfo[]>();

  for (const player of players) {
    const info = tiers.get(player.normalized_name);
    if (!info) continue;
    const group = byPosition.get(player.pos);
    if (group) {
      group.push(info);
    } else {
      byPosition.set(player.pos, [info]);
    }
  }

  const scarcity: Scarcity[] = [];

  for (const [pos, infos] of byPosition) {
    // Only the top tier still on the board matters. That is the run you are
    // deciding whether to wait out; tiers below it are a different decision.
    const bestTier = Math.min(...infos.map((info) => info.tier));
    const inTier = infos.filter((info) => info.tier === bestTier);
    const edge = inTier.find((info) => info.isLastOfTier);

    scarcity.push({
      pos,
      remaining: inTier.length,
      dropToNext: edge?.dropToNext ?? null,
    });
  }

  return scarcity.sort((a, b) => a.remaining - b.remaining);
}
