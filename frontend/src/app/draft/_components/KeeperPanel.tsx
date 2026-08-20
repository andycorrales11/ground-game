'use client';

import type { KeeperPick } from '@/lib/types';

import Panel from './Panel';

/*
  The picks nobody makes.

  This panel exists to explain the room's own numbering. A keeper draft opens on
  pick 4 and jumps from 20 to 25, and without somewhere to see why, that reads as
  a bug rather than as four players already being spoken for.

  Picks are labelled the way the draft sheet is -- round and *seat* -- because
  that is how the keeper file is written and how a league talks about them. Note
  this is not Sleeper's labelling, which counts position within the round.
*/

interface Props {
  keepers: KeeperPick[];
}

export default function KeeperPanel({ keepers }: Props) {
  // A league without keepers is the normal case. Say nothing rather than
  // rendering an empty table for it.
  if (!keepers || keepers.length === 0) return null;

  const mine = keepers.filter((keeper) => keeper.is_user).length;

  return (
    <Panel
      title="Keepers"
      aside={
        <span className="tabular text-xs text-dim">
          {mine > 0 ? `${mine} yours · ` : ''}
          {keepers.length}
        </span>
      }
    >
      <div className="max-h-72 overflow-y-auto">
        <table className="w-full border-collapse">
          <caption className="sr-only">
            Players already kept, and the pick each one costs
          </caption>
          <thead>
            <tr className="border-b border-line">
              <th
                scope="col"
                className="font-display px-3 py-1.5 text-left text-[10px] font-semibold uppercase tracking-[0.14em] text-dim"
              >
                Pick
              </th>
              <th
                scope="col"
                className="font-display px-3 py-1.5 text-left text-[10px] font-semibold uppercase tracking-[0.14em] text-dim"
              >
                Player
              </th>
              <th
                scope="col"
                className="font-display px-3 py-1.5 text-right text-[10px] font-semibold uppercase tracking-[0.14em] text-dim"
              >
                Kept by
              </th>
            </tr>
          </thead>
          <tbody>
            {keepers.map((keeper) => (
              <tr
                key={keeper.overall}
                className={`border-b border-line/50 last:border-0 ${
                  keeper.is_user ? 'bg-line/30' : ''
                }`}
              >
                <td className="tabular whitespace-nowrap px-3 py-1.5 text-xs text-dim">
                  {keeper.round}.{String(keeper.pick).padStart(2, '0')}
                </td>
                <td className="px-3 py-1.5 text-xs text-chalk">{keeper.player}</td>
                <td
                  className={`whitespace-nowrap px-3 py-1.5 text-right text-xs ${
                    keeper.is_user ? 'text-chalk' : 'text-dim'
                  }`}
                >
                  {keeper.is_user ? 'You' : keeper.manager ?? '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="border-t border-line px-3 py-2 text-[11px] leading-relaxed text-dim">
        Round and seat, as the keeper file is written — not Sleeper&apos;s
        position-within-the-round. These picks are already spent, so the clock
        steps over them.
      </p>
    </Panel>
  );
}
