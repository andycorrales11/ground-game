'use client';

import { positionStyle } from '@/lib/positions';
import type { LivePick } from '@/lib/types';

import Panel from './Panel';

interface Props {
  picks: LivePick[];
  /** When Sleeper was last asked for picks. Null before the first poll lands. */
  lastSync: Date | null;
}

/** Live mode only: what the rest of the league has done since you last looked. */
export default function RecentPicks({ picks, lastSync }: Props) {
  if (picks.length === 0) return null;

  return (
    <Panel
      title="From Sleeper"
      aside={
        lastSync && (
          <span className="tabular text-xs text-dim">{lastSync.toLocaleTimeString()}</span>
        )
      }
    >
      <ul className="divide-y divide-line/40">
        {picks.map((pick) => (
          <li key={pick.pick_number} className="flex items-baseline gap-2 px-3 py-1.5 text-xs">
            <span className="tabular w-7 shrink-0 text-dim">{pick.pick_number}</span>
            <span
              className={`font-display w-8 shrink-0 font-semibold uppercase tracking-[0.1em] ${
                positionStyle(pick.position).text
              }`}
            >
              {pick.position}
            </span>
            <span className="text-chalk">{pick.player_name}</span>
            <span className="ml-auto shrink-0 text-dim">Team {pick.roster_id}</span>
          </li>
        ))}
      </ul>
    </Panel>
  );
}
