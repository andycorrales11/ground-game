'use client';

import { useCallback, useEffect, useState } from 'react';

import { errorMessage, fetchResults } from '@/lib/api';
import { positionStyle } from '@/lib/positions';
import type { DraftMode, DraftResults, RosterSlot, TeamResult } from '@/lib/types';

/*
  Every team's roster, side by side.

  Fetched on demand rather than carried on the draft state: it is twelve rosters,
  and the state call already runs on every filter change and every live poll.

  It is available during the draft, not only after it. "What has everyone else
  got" is a question you ask hardest on the clock -- it is how you work out
  whether the run you are worried about is actually coming.
*/

interface Props {
  mode: DraftMode;
  sessionId: string;
  /** Bumped by the parent after each pick so the open table refreshes itself. */
  refreshKey: number;
  onClose: () => void;
}

function slotPosition(slot: RosterSlot): string {
  return slot.pos ?? slot.slot.replace(/\d+$/, '');
}

function TeamCard({ team, kept }: { team: TeamResult; kept: Set<string> }) {
  const filled = team.roster.filter((slot) => slot.player).length;

  return (
    <section
      className={`border bg-deck ${team.is_user ? 'border-chalk' : 'border-line'}`}
    >
      <header className="flex items-baseline justify-between gap-2 border-b border-line px-3 py-2">
        <h3 className="font-display truncate text-xs font-semibold uppercase tracking-[0.14em] text-chalk">
          {team.name}
          {team.is_user && <span className="ml-1.5 text-dim">(you)</span>}
        </h3>
        <span className="tabular shrink-0 text-[11px] text-dim">{filled}</span>
      </header>

      <table className="w-full border-collapse">
        <caption className="sr-only">{team.name}&apos;s roster by slot</caption>
        <tbody>
          {team.roster.map((slot) => {
            const style = positionStyle(slotPosition(slot));
            const isKeeper = slot.player !== null && kept.has(slot.player);
            return (
              <tr key={slot.slot} className="border-b border-line/40 last:border-0">
                <td
                  className={`font-display w-12 border-l-[3px] px-2 py-1 text-[10px] uppercase tracking-[0.1em] ${style.bar} ${style.text}`}
                >
                  {slot.slot}
                </td>
                <td className="px-2 py-1 text-xs text-chalk">
                  {slot.player ?? <span className="text-dim">—</span>}
                  {/*
                    Keepers are marked because a roster full of players nobody
                    saw drafted is otherwise unreadable -- four of these were
                    never on the board.
                  */}
                  {isKeeper && (
                    <span
                      title="Kept, not drafted"
                      className="font-display ml-1.5 text-[9px] uppercase tracking-[0.1em] text-dim"
                    >
                      K
                    </span>
                  )}
                </td>
                <td className="tabular w-8 px-2 py-1 text-right text-[11px] text-dim">
                  {slot.bye ?? ''}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </section>
  );
}

export default function ResultsBoard({ mode, sessionId, refreshKey, onClose }: Props) {
  const [results, setResults] = useState<DraftResults | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setResults(await fetchResults(mode, sessionId));
      setError(null);
    } catch (err) {
      setError(errorMessage(err, 'Could not load the draft results.'));
    }
  }, [mode, sessionId]);

  useEffect(() => {
    void load();
  }, [load, refreshKey]);

  return (
    <section className="border border-line bg-deck">
      <header className="flex items-baseline justify-between gap-3 border-b border-line px-3 py-2">
        <h2 className="font-display text-xs font-semibold uppercase tracking-[0.18em] text-dim">
          Every team
        </h2>
        <div className="flex items-baseline gap-3">
          {results && (
            <span className="tabular text-[11px] text-dim">
              {results.status === 'completed'
                ? 'Final'
                : `Through pick ${results.current_pick_num}`}
            </span>
          )}
          <button
            type="button"
            onClick={onClose}
            className="font-display border border-line px-2 py-1 text-[11px] uppercase tracking-[0.14em] text-chalk transition-colors hover:bg-line"
          >
            Back to board
          </button>
        </div>
      </header>

      {error && (
        <p role="alert" className="px-3 py-3 text-sm text-chalk">
          {error}
        </p>
      )}

      {!results && !error && (
        <p className="px-3 py-3 text-sm text-dim">Loading rosters…</p>
      )}

      {results?.rosters_are_partial && (
        <p className="border-b border-line px-3 py-2 text-[11px] leading-relaxed text-dim">
          Sleeper owns the rosters in a live draft, so only your team is filled
          in here.
        </p>
      )}

      {results && (
        <div className="grid gap-3 p-3 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4">
          {results.teams.map((team) => (
            <TeamCard
              key={team.team_index}
              team={team}
              kept={new Set(team.keepers)}
            />
          ))}
        </div>
      )}
    </section>
  );
}
