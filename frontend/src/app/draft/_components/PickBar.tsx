'use client';

import { positionStyle } from '@/lib/positions';
import type { Player } from '@/lib/types';

interface Props {
  player: Player | null;
  /** False when it is not your turn -- the backend would draft for whoever is on the clock. */
  canPick: boolean;
  /** "Draft" in a simulation, "Record" against a live Sleeper draft. */
  actionVerb: string;
  /** Why the action is unavailable, when it is. */
  blockedReason: string | null;
  isBusy: boolean;
  onConfirm: () => void;
  onClear: () => void;
}

/*
  Replaces typing the player's name into a text box and hoping it matched. The
  board already shows the name; the only thing left to do with it is confirm.
*/
export default function PickBar({
  player,
  canPick,
  actionVerb,
  blockedReason,
  isBusy,
  onConfirm,
  onClear,
}: Props) {
  return (
    <div className="sticky bottom-0 z-10 flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-line bg-deck px-3 py-2.5">
      {player ? (
        <>
          <span
            className={`font-display text-xs font-semibold uppercase tracking-[0.1em] ${
              positionStyle(player.pos).text
            }`}
          >
            {player.pos}
          </span>
          <span className="text-sm text-chalk">{player.display_name}</span>
          <span className="tabular text-xs text-dim">
            {player.team ?? '—'}
            {player.bye !== null && ` · bye ${player.bye}`}
          </span>

          <div className="ml-auto flex items-center gap-2">
            <button
              type="button"
              onClick={onClear}
              className="font-display px-2 py-1 text-xs uppercase tracking-[0.12em] text-dim transition-colors hover:text-chalk"
            >
              Clear
            </button>
            <button
              type="button"
              onClick={onConfirm}
              disabled={!canPick || isBusy}
              className="font-display bg-chalk px-3 py-1.5 text-xs font-semibold uppercase tracking-[0.12em] text-pitch transition-opacity disabled:cursor-not-allowed disabled:opacity-35"
            >
              {isBusy ? 'Working' : `${actionVerb} ${player.display_name}`}
              <span className="ml-2 opacity-60">⏎</span>
            </button>
          </div>

          {!canPick && blockedReason && (
            <p className="w-full text-xs text-dim">{blockedReason}</p>
          )}
        </>
      ) : (
        /* An empty bar is an invitation, so it says what to do rather than sitting blank. */
        <p className="text-xs text-dim">
          Select a player to {actionVerb.toLowerCase()} — click a row, or press{' '}
          <kbd className="tabular border border-line px-1">↑</kbd>{' '}
          <kbd className="tabular border border-line px-1">↓</kbd>
        </p>
      )}
    </div>
  );
}
