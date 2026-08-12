'use client';

import { Fragment, useEffect } from 'react';

import { integer, num, signed } from '@/lib/format';
import { positionStyle } from '@/lib/positions';
import type { TierInfo } from '@/lib/tiers';
import type { Player } from '@/lib/types';

import CliffRule from './CliffRule';

/** POS, PLAYER, TEAM, BYE, ADP, PROJ, VORP, VONA -- what a cliff rule has to span. */
const COLUMN_COUNT = 8;

export function rowId(normalizedName: string): string {
  return `board-row-${normalizedName}`;
}

/*
  Read left to right, these go from the market's opinion to yours: where the
  field is taking them, what they are projected to score, what that is worth
  against replacement, and what waiting costs. Proj sits next to VORP on purpose
  -- VORP is derived from it, and the gap between the two columns is the whole
  argument for drafting a tight end over a better-scoring wide receiver.
*/
const METRICS = [
  { key: 'ADP', label: 'ADP', hint: 'Average draft position. Lower is earlier.' },
  {
    key: 'PTS',
    label: 'Proj',
    hint: "Projected total fantasy points for the season, in this league's scoring.",
  },
  {
    key: 'VORP',
    label: 'VORP',
    hint: 'Projected points above the replacement-level player at this position.',
  },
  { key: 'VONA', label: 'VONA', hint: 'What waiting until your next pick costs you.' },
] as const;

interface Props {
  players: Player[];
  tiers: Map<string, TierInfo>;
  /** False when tiers would not read down the page in order. See tiersAreInReadingOrder. */
  showCliffs: boolean;
  /**
   * Whether VONA means anything yet.
   *
   * It only does on your turn. Off-turn the backend has no next turn to
   * simulate towards, so it leaves picks_to_simulate at zero and every
   * candidate is compared against itself -- a board of exact zeroes. Printing
   * those would say waiting costs nothing, which is the opposite of true.
   */
  vonaComputed: boolean;
  sortBy: string;
  selectedName: string | null;
  onSelect: (normalizedName: string) => void;
  onConfirm: (player: Player) => void;
}

export default function PlayerBoard({
  players,
  tiers,
  showCliffs,
  vonaComputed,
  sortBy,
  selectedName,
  onSelect,
  onConfirm,
}: Props) {
  // Keeping the selection visible is the whole point of arrow-key navigation.
  useEffect(() => {
    if (!selectedName) return;
    document.getElementById(rowId(selectedName))?.scrollIntoView({ block: 'nearest' });
  }, [selectedName]);

  if (players.length === 0) {
    return (
      <div className="px-3 py-16 text-center">
        <p className="font-display text-sm uppercase tracking-[0.16em] text-dim">
          Nothing on the board matches
        </p>
        <p className="mt-2 text-sm text-dim">
          Clear the filter, or pick a different position.
        </p>
      </div>
    );
  }

  /*
    overflow-auto on both axes, stated rather than inherited: setting only
    overflow-y makes CSS promote overflow-x from visible to auto anyway, which
    works but reads like an accident. The min-width is what makes it matter --
    without it eight columns compress into a phone's width instead of scrolling,
    and the page itself never gains a horizontal scrollbar either way.
  */
  return (
    <div className="board-scroll max-h-[62vh] overflow-auto xl:max-h-[calc(100vh-15rem)]">
      <table
        role="grid"
        tabIndex={0}
        aria-label="Available players"
        aria-activedescendant={selectedName ? rowId(selectedName) : undefined}
        className="w-full min-w-[680px] border-collapse"
      >
        <thead>
          <tr className="bg-deck">
            {['Pos', 'Player', 'Team', 'Bye'].map((label) => (
              <th
                key={label}
                scope="col"
                className="font-display sticky top-0 z-10 border-b border-line bg-deck px-2 py-2 text-left text-[11px] font-semibold uppercase tracking-[0.16em] text-dim"
              >
                {label}
              </th>
            ))}
            {METRICS.map((metric) => (
              <th
                key={metric.key}
                scope="col"
                /*
                  The column you sorted by is the one you are reasoning about, so
                  it is the one that gets chalk. The other two stay dim rather
                  than competing for the same glance.
                */
                aria-sort={sortBy === metric.key ? 'descending' : 'none'}
                title={
                  metric.key === 'VONA' && !vonaComputed
                    ? 'Value over next available is worked out when it is your pick.'
                    : metric.hint
                }
                className={`font-display sticky top-0 z-10 border-b border-line bg-deck px-2 py-2 text-right text-[11px] font-semibold uppercase tracking-[0.16em] ${
                  sortBy === metric.key ? 'text-chalk' : 'text-dim'
                } ${metric.key === 'VONA' && !vonaComputed ? 'opacity-50' : ''}`}
              >
                {metric.label}
              </th>
            ))}
          </tr>
        </thead>

        <tbody>
          {players.map((player) => {
            const info = tiers.get(player.normalized_name);
            const selected = player.normalized_name === selectedName;
            const style = positionStyle(player.pos);
            const cliff = showCliffs && info?.isLastOfTier && info.dropToNext !== null;

            return (
              <Fragment key={player.normalized_name}>
                <tr
                  id={rowId(player.normalized_name)}
                  role="row"
                  aria-selected={selected}
                  onClick={() => onSelect(player.normalized_name)}
                  onDoubleClick={() => onConfirm(player)}
                  className={`cursor-pointer border-b border-line/50 transition-colors ${
                    selected ? 'bg-line' : 'hover:bg-line/50'
                  }`}
                >
                  <td
                    role="gridcell"
                    className={`border-l-[3px] py-1.5 pr-2 pl-2.5 ${style.bar}`}
                  >
                    {/*
                      The label, not just the bar. Position is the one thing on
                      this page carried by colour, so it is also always carried
                      by a word -- the hue is the fast read, never the only one.
                    */}
                    <span
                      className={`font-display text-xs font-semibold uppercase tracking-[0.1em] ${style.text}`}
                    >
                      {player.pos}
                    </span>
                  </td>
                  <td role="gridcell" className="py-1.5 pr-3 text-sm text-chalk">
                    {player.display_name}
                  </td>
                  <td role="gridcell" className="tabular py-1.5 pr-3 text-xs text-dim">
                    {player.team ?? '—'}
                  </td>
                  <td role="gridcell" className="tabular py-1.5 pr-3 text-xs text-dim">
                    {integer(player.bye)}
                  </td>
                  {METRICS.map((metric) => (
                    <td
                      key={metric.key}
                      role="gridcell"
                      className={`tabular py-1.5 pr-2 text-right text-xs ${
                        sortBy === metric.key ? 'text-chalk' : 'text-dim'
                      }`}
                    >
                      {metric.key === 'VONA'
                        ? vonaComputed
                          ? signed(player.VONA)
                          : '—'
                        : num(player[metric.key] as number | null)}
                    </td>
                  ))}
                </tr>

                {cliff && info && info.dropToNext !== null && (
                  <CliffRule
                    tier={info.tier}
                    pos={player.pos}
                    drop={info.dropToNext}
                    colSpan={COLUMN_COUNT}
                  />
                )}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
