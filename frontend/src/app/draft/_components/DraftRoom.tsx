'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useParams } from 'next/navigation';

import {
  errorMessage,
  fetchDraftState,
  pollLiveDraft,
  simulateNextPick,
  submitPick,
} from '@/lib/api';
import { POSITIONS } from '@/lib/positions';
import { assignTiers, scarcityByPosition, tiersAreInReadingOrder } from '@/lib/tiers';
import type { DraftMode, DraftState, LivePick, Player } from '@/lib/types';

import BoardFilters from './BoardFilters';
import ClockRail from './ClockRail';
import PickBar from './PickBar';
import PlayerBoard from './PlayerBoard';
import RecentPicks from './RecentPicks';
import RosterPanel from './RosterPanel';
import ScarcityStrip from './ScarcityStrip';

/*
  How often to ask Sleeper for new picks. Deliberately unhurried: the board
  refresh that follows a new pick runs a forward simulation of every CPU pick
  until your next turn, so polling harder just stacks expensive work.
*/
const POLL_INTERVAL_MS = 8000;

/** How many of Sleeper's picks to keep on screen. */
const RECENT_PICK_LIMIT = 12;

interface ModeConfig {
  /** Whether real opponents exist and have to be polled for. */
  polls: boolean;
  /** Simulation drives its CPUs by hand; the backend rejects this for live sessions. */
  canSimulateCpu: boolean;
  /** The verb stays the same from the button to the confirmation. */
  actionVerb: string;
  /** Shown on your turn, when the mode needs you to do something elsewhere. */
  turnNote: string | null;
}

const MODES: Record<DraftMode, ModeConfig> = {
  simulation: {
    polls: false,
    canSimulateCpu: true,
    actionVerb: 'Draft',
    turnNote: null,
  },
  live: {
    polls: true,
    canSimulateCpu: false,
    actionVerb: 'Record',
    turnNote:
      'Make the pick in Sleeper. It syncs here on its own, or record it to update the board now.',
  },
};

function onClockLabel(state: DraftState): string {
  const team = state.on_clock_team;
  // Nobody is on the clock once the draft is over, and the rail says so itself.
  if (!team) return 'Nobody';
  if (team.type === 'cpu') {
    const which = team.team_index !== undefined ? team.team_index + 1 : team.roster_id;
    return `CPU (Team ${which})`;
  }
  // Live sessions identify teams by Sleeper roster id, simulations by slot index.
  const which = team.roster_id ?? (team.team_index !== undefined ? team.team_index + 1 : '?');
  return `Team ${which}`;
}

interface Props {
  mode: DraftMode;
}

/*
  One room, two modes.

  Simulation and live were previously two 200-line pages that differed in a poll
  loop, a button and some wording, which meant every fix had to be made twice
  and usually was not. What actually varies lives in MODES above.
*/
export default function DraftRoom({ mode }: Props) {
  const config = MODES[mode];
  const params = useParams<{ session_id: string }>();
  const sessionId = typeof params.session_id === 'string' ? params.session_id : '';

  const [draftState, setDraftState] = useState<DraftState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isPending, setIsPending] = useState(false);
  const [isBusy, setIsBusy] = useState(false);

  const [positionFilter, setPositionFilter] = useState('ALL');
  const [sortBy, setSortBy] = useState('ADP');
  const [query, setQuery] = useState('');
  const [selectedName, setSelectedName] = useState<string | null>(null);

  const [recentPicks, setRecentPicks] = useState<LivePick[]>([]);
  const [lastSync, setLastSync] = useState<Date | null>(null);

  const queryInputRef = useRef<HTMLInputElement | null>(null);

  /*
    The board is never torn down to reload it. Setting draftState back to null
    here is what used to replace the whole room with "Loading draft..." every
    time a filter changed -- mid-draft, with a clock running.
  */
  const load = useCallback(async () => {
    if (!sessionId) return;
    setIsPending(true);
    try {
      const data = await fetchDraftState(mode, sessionId, { positionFilter, sortBy });
      setDraftState(data);
      setError(null);
    } catch (err) {
      setError(errorMessage(err, 'Could not load the draft board.'));
    } finally {
      setIsPending(false);
      setIsLoading(false);
    }
  }, [mode, sessionId, positionFilter, sortBy]);

  useEffect(() => {
    void load();
  }, [load]);

  /*
    The poll interval is kept off `load`'s identity on purpose. Depending on it
    directly would tear down and restart the timer on every filter change, so a
    drafter flicking between positions could hold off a Sleeper sync indefinitely.
  */
  const loadRef = useRef(load);
  useEffect(() => {
    loadRef.current = load;
  }, [load]);

  const pollInFlight = useRef(false);

  useEffect(() => {
    if (!config.polls || !sessionId) return;

    let cancelled = false;

    const tick = async () => {
      // A board refresh on your turn can outlast the interval; stacking those
      // requests is what makes the page crawl exactly when it matters.
      if (pollInFlight.current) return;
      pollInFlight.current = true;
      try {
        const picks = await pollLiveDraft(sessionId);
        if (cancelled) return;
        setLastSync(new Date());
        if (picks.length > 0) {
          setRecentPicks((prev) =>
            [...picks].reverse().concat(prev).slice(0, RECENT_PICK_LIMIT),
          );
          await loadRef.current();
        }
      } catch {
        // A dropped poll is not worth interrupting the board for. The next one
        // is eight seconds away, and it will catch up on everything missed.
      } finally {
        pollInFlight.current = false;
      }
    };

    const id = setInterval(tick, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [config.polls, sessionId]);

  const players = useMemo(() => draftState?.available_players ?? [], [draftState]);

  // Tiers come off the whole returned board, never the text-filtered view --
  // typing a name should narrow what you see, not redraw where the cliffs are.
  const tiers = useMemo(() => assignTiers(players), [players]);
  const scarcity = useMemo(() => scarcityByPosition(players, tiers), [players, tiers]);

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return players;
    return players.filter(
      (player) =>
        player.display_name.toLowerCase().includes(needle) ||
        (player.team ?? '').toLowerCase().includes(needle),
    );
  }, [players, query]);

  /*
    Cliffs need a contiguous run of one position, read in tier order. A text
    filter punches holes in the run, and ALL or FLEX interleaves positions that
    were never competing for the same slot -- in both cases the scarcity strip
    carries the same information without claiming an adjacency that is not there.
  */
  const isSinglePosition = (POSITIONS as readonly string[]).includes(positionFilter);
  const showCliffs =
    isSinglePosition && query.trim() === '' && tiersAreInReadingOrder(visible, tiers);

  const selectedPlayer = useMemo(
    () => visible.find((player) => player.normalized_name === selectedName) ?? null,
    [visible, selectedName],
  );

  // Somebody else took them, or a filter hid them. Either way the pick bar
  // should not keep offering a player who is no longer on the board.
  useEffect(() => {
    if (selectedName && !players.some((p) => p.normalized_name === selectedName)) {
      setSelectedName(null);
    }
  }, [players, selectedName]);

  const isUserTurn = draftState?.is_user_turn ?? false;
  const isComplete = draftState?.status === 'completed';

  const confirmPick = useCallback(
    async (player: Player) => {
      if (!sessionId || isBusy || !isUserTurn) return;
      setIsBusy(true);
      try {
        // display_name is what the board shows and what the backend normalises
        // on the way in, so there is nothing to translate here.
        await submitPick(mode, sessionId, player.display_name);
        setSelectedName(null);
        await load();
      } catch (err) {
        setError(errorMessage(err, `Could not draft ${player.display_name}.`));
      } finally {
        setIsBusy(false);
      }
    },
    [mode, sessionId, isBusy, isUserTurn, load],
  );

  const runCpuPick = useCallback(async () => {
    if (!sessionId || isBusy) return;
    setIsBusy(true);
    try {
      await simulateNextPick(sessionId);
      await load();
    } catch (err) {
      setError(errorMessage(err, 'Could not simulate the next pick.'));
    } finally {
      setIsBusy(false);
    }
  }, [sessionId, isBusy, load]);

  const syncNow = useCallback(async () => {
    if (!sessionId || isBusy) return;
    setIsBusy(true);
    try {
      const picks = await pollLiveDraft(sessionId);
      setLastSync(new Date());
      if (picks.length > 0) {
        setRecentPicks((prev) => [...picks].reverse().concat(prev).slice(0, RECENT_PICK_LIMIT));
      }
      await load();
    } catch (err) {
      setError(errorMessage(err, 'Could not reach Sleeper.'));
    } finally {
      setIsBusy(false);
    }
  }, [sessionId, isBusy, load]);

  const moveSelection = useCallback(
    (delta: number) => {
      if (visible.length === 0) return;
      const index = visible.findIndex((player) => player.normalized_name === selectedName);
      const next =
        index === -1
          ? delta > 0
            ? 0
            : visible.length - 1
          : Math.min(visible.length - 1, Math.max(0, index + delta));
      setSelectedName(visible[next].normalized_name);
    },
    [visible, selectedName],
  );

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target;
      const typing =
        target instanceof HTMLInputElement ||
        target instanceof HTMLTextAreaElement ||
        target instanceof HTMLSelectElement;

      // Escape works everywhere: out of the filter box first, then the selection.
      if (event.key === 'Escape') {
        if (typing) {
          (target as HTMLElement).blur();
        } else {
          setSelectedName(null);
        }
        return;
      }

      if (typing) return;

      if (event.key === '/') {
        event.preventDefault();
        queryInputRef.current?.focus();
        return;
      }

      if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
        event.preventDefault();
        moveSelection(event.key === 'ArrowDown' ? 1 : -1);
        return;
      }

      if (event.key === 'Enter' && selectedPlayer) {
        event.preventDefault();
        void confirmPick(selectedPlayer);
      }
    };

    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [moveSelection, selectedPlayer, confirmPick]);

  if (isLoading) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-pitch px-4">
        <p className="font-display text-sm uppercase tracking-[0.2em] text-dim">
          {mode === 'live' ? 'Connecting to your Sleeper draft' : 'Building the board'}
        </p>
      </main>
    );
  }

  if (!draftState) {
    return (
      <main className="flex min-h-screen flex-col items-center justify-center gap-3 bg-pitch px-4 text-center">
        <p className="font-display text-sm uppercase tracking-[0.2em] text-chalk">
          This draft could not be loaded
        </p>
        <p className="max-w-md text-sm text-dim">
          {error ?? 'The session may have expired — draft state is held in memory and does not survive a backend restart.'}
        </p>
      </main>
    );
  }

  /*
    Rounds are derivable only when the backend reports the league size. Without
    it the rail shows the pick number alone rather than guessing.
  */
  const round = draftState.teams
    ? Math.floor((draftState.current_pick_num - 1) / draftState.teams) + 1
    : null;

  const showSimulateButton = config.canSimulateCpu && !isUserTurn && !isComplete;

  return (
    <div className="min-h-screen bg-pitch">
      <ClockRail
        pickNum={draftState.current_pick_num}
        totalPicks={draftState.total_picks}
        round={round}
        isUserTurn={isUserTurn}
        onClockLabel={onClockLabel(draftState)}
        isComplete={isComplete}
        isPending={isPending}
        error={error}
      >
        {showSimulateButton && (
          <button
            type="button"
            onClick={runCpuPick}
            disabled={isBusy}
            className="font-display border border-line px-3 py-1 text-xs font-semibold uppercase tracking-[0.12em] text-chalk transition-colors hover:bg-line disabled:opacity-40"
          >
            {isBusy ? 'Working' : 'Simulate next pick'}
          </button>
        )}
        {config.polls && (
          <button
            type="button"
            onClick={syncNow}
            disabled={isBusy}
            className={`font-display border px-3 py-1 text-xs font-semibold uppercase tracking-[0.12em] transition-colors disabled:opacity-40 ${
              isUserTurn
                ? 'border-pitch/30 text-pitch hover:bg-pitch/10'
                : 'border-line text-chalk hover:bg-line'
            }`}
            title={lastSync ? `Last checked ${lastSync.toLocaleTimeString()}` : undefined}
          >
            Sync now
          </button>
        )}
      </ClockRail>

      <main className="mx-auto grid max-w-[1600px] gap-4 px-4 py-4 xl:grid-cols-[minmax(0,1fr)_340px]">
        <section className="border border-line bg-deck">
          <BoardFilters
            positionFilter={positionFilter}
            onPositionFilterChange={setPositionFilter}
            sortBy={sortBy}
            onSortByChange={setSortBy}
            query={query}
            onQueryChange={setQuery}
            queryInputRef={queryInputRef}
            showing={visible.length}
          />

          {!showCliffs && <ScarcityStrip scarcity={scarcity} />}

          <PlayerBoard
            players={visible}
            tiers={tiers}
            showCliffs={showCliffs}
            sortBy={sortBy}
            selectedName={selectedName}
            onSelect={setSelectedName}
            onConfirm={confirmPick}
          />

          {isUserTurn && config.turnNote && (
            <p className="border-t border-line px-3 py-2 text-xs text-dim">{config.turnNote}</p>
          )}

          <PickBar
            player={selectedPlayer}
            canPick={isUserTurn && !isComplete}
            actionVerb={config.actionVerb}
            blockedReason={
              isComplete
                ? 'The draft is over.'
                : `Waiting on ${onClockLabel(draftState)}.`
            }
            isBusy={isBusy}
            onConfirm={() => selectedPlayer && void confirmPick(selectedPlayer)}
            onClear={() => setSelectedName(null)}
          />
        </section>

        <aside className="space-y-4">
          <RosterPanel roster={draftState.user_roster} byeConflicts={draftState.bye_conflicts} />
          {config.polls && <RecentPicks picks={recentPicks} lastSync={lastSync} />}
        </aside>
      </main>
    </div>
  );
}
