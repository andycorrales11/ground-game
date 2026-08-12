'use client';

interface Props {
  pickNum: number;
  totalPicks: number;
  /** Null when the backend has not told us the league size; the rail just omits it. */
  round: number | null;
  isUserTurn: boolean;
  /** Who is picking, already phrased -- "Team 4", "CPU (Team 7)". */
  onClockLabel: string;
  isComplete: boolean;
  isPending: boolean;
  error: string | null;
  children?: React.ReactNode;
}

/*
  The rail carries one piece of information above all others: whether it is your
  pick. It does that by inverting -- a bright bar across the top of an otherwise
  dark room -- rather than by turning a colour, because colour on this page is
  reserved for position and spending it here would make the board's hues mean
  two things at once.
*/
export default function ClockRail({
  pickNum,
  totalPicks,
  round,
  isUserTurn,
  onClockLabel,
  isComplete,
  isPending,
  error,
  children,
}: Props) {
  const live = isUserTurn && !isComplete;

  return (
    <header
      className={`sticky top-0 z-20 border-b border-line ${
        live ? 'bg-chalk text-pitch' : 'bg-deck text-chalk'
      }`}
    >
      <div className="mx-auto flex max-w-[1600px] flex-wrap items-center gap-x-6 gap-y-2 px-4 py-2.5">
        <span className="font-display text-sm font-bold uppercase tracking-[0.28em]">
          Ground Game
        </span>

        <span
          className={`tabular text-xs ${live ? 'text-pitch/70' : 'text-dim'}`}
          aria-label={`Pick ${pickNum} of ${totalPicks}`}
        >
          {round !== null && <span className="mr-2">RD {round}</span>}
          PICK {pickNum} / {totalPicks}
        </span>

        <div className="ml-auto flex items-center gap-3">
          {isComplete ? (
            <span className="font-display text-sm font-semibold uppercase tracking-[0.18em]">
              Draft complete
            </span>
          ) : (
            <span
              className={`font-display text-sm font-semibold uppercase tracking-[0.18em] ${
                live ? '' : 'text-dim'
              }`}
              // The turn changes without the page changing, so it has to announce itself.
              aria-live="polite"
            >
              <span className={live ? 'clock-live mr-1.5 inline-block' : 'mr-1.5 inline-block'}>
                ●
              </span>
              {live ? "You're on the clock" : `${onClockLabel} on the clock`}
            </span>
          )}
          {children}
        </div>
      </div>

      {/*
        Refetch state lives here rather than over the board, so the board stays
        readable while it reloads. Aria-hidden: the polite region above already
        says what changed, and a spinner that announces itself every eight
        seconds during a live draft is noise.
      */}
      <div className="h-px w-full overflow-hidden" aria-hidden="true">
        {isPending && (
          <span
            className={`rail-sweep block h-px w-1/5 ${live ? 'bg-pitch/40' : 'bg-chalk/60'}`}
          />
        )}
      </div>

      {error && (
        <p
          role="alert"
          className="border-t border-line bg-pitch px-4 py-2 text-sm text-chalk"
        >
          <span className="hazard-severe mr-2 inline-block h-3 w-3 translate-y-0.5" />
          {error}
        </p>
      )}
    </header>
  );
}
