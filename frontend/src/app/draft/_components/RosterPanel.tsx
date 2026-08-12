'use client';

import { integer } from '@/lib/format';
import { positionStyle } from '@/lib/positions';
import type { RosterSlot } from '@/lib/types';

import ByeConflicts, { severityClass } from './ByeConflicts';
import Panel from './Panel';

/*
  Slot names carry their depth -- "RB1", "WR2", "BN3" -- but the hue belongs to
  the position, so the digits come off before the lookup. A slot the board does
  not project (bench, flex) falls through to steel, which is right: it has no one
  position to be coloured by until somebody is in it.
*/
function slotPosition(slot: RosterSlot): string {
  return slot.pos ?? slot.slot.replace(/\d+$/, '');
}

interface Props {
  roster: RosterSlot[];
  byeConflicts: Record<string, string[]>;
}

export default function RosterPanel({ roster, byeConflicts }: Props) {
  /*
    Live mode does not populate the roster -- Sleeper owns it -- except for the
    user's own team. An empty roster is a state to stay quiet about, not to
    render an empty table for.
  */
  if (!roster || roster.length === 0) return null;

  const filled = roster.filter((slot) => slot.player).length;

  const conflictCount = (bye: number | null): number =>
    bye === null ? 0 : (byeConflicts?.[String(bye)]?.length ?? 0);

  return (
    <Panel
      title="Your roster"
      aside={
        <span className="tabular text-xs text-dim">
          {filled} / {roster.length}
        </span>
      }
    >
      <table className="w-full border-collapse">
        <caption className="sr-only">Your drafted players by roster slot</caption>
        <tbody>
          {roster.map((slot) => {
            const style = positionStyle(slotPosition(slot));
            const clash = conflictCount(slot.bye);

            return (
              <tr key={slot.slot} className="border-b border-line/40 last:border-b-0">
                <td className={`border-l-[3px] py-1.5 pr-2 pl-2.5 ${style.bar}`}>
                  <span
                    className={`font-display text-[11px] font-semibold uppercase tracking-[0.1em] ${style.text}`}
                  >
                    {slot.slot}
                  </span>
                </td>
                <td className="py-1.5 pr-2 text-sm">
                  {slot.player ? (
                    <span className="text-chalk">{slot.player}</span>
                  ) : (
                    <span className="text-dim">empty</span>
                  )}
                </td>
                <td className="tabular py-1.5 pr-3 text-right text-xs">
                  {slot.bye !== null && clash > 0 ? (
                    <span
                      className="inline-flex items-center gap-1.5"
                      title={`${clash} of your players are out in week ${slot.bye}`}
                    >
                      <span
                        className={`${severityClass(clash)} inline-block h-2.5 w-4`}
                        aria-hidden="true"
                      />
                      <span className={clash >= 3 ? 'font-semibold text-chalk' : 'text-chalk/80'}>
                        {slot.bye}
                      </span>
                    </span>
                  ) : (
                    <span className="text-dim">{slot.player ? integer(slot.bye) : ''}</span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      <ByeConflicts byeConflicts={byeConflicts} />
    </Panel>
  );
}
