import { positionStyle } from '@/lib/positions';
import type { Scarcity } from '@/lib/tiers';

interface Props {
  scarcity: Scarcity[];
}

/*
  The cliff, aggregated.

  An unfiltered board interleaves positions, so a rule drawn across it would
  separate players who were never competing for the same slot. The same
  information survives as a count: how deep each position's best remaining tier
  still is, thinnest first, because the thinnest one is the decision.
*/
export default function ScarcityStrip({ scarcity }: Props) {
  if (scarcity.length === 0) return null;

  return (
    <div className="flex flex-wrap items-baseline gap-x-5 gap-y-2 border-b border-line px-3 py-2">
      <span className="font-display text-[11px] font-semibold uppercase tracking-[0.16em] text-dim">
        Tier depth
      </span>

      {scarcity.map((entry) => (
        <span key={entry.pos} className="flex items-baseline gap-1.5 text-xs">
          <span
            className={`font-display font-semibold uppercase tracking-[0.1em] ${
              positionStyle(entry.pos).text
            }`}
          >
            {entry.pos}
          </span>
          <span className="tabular text-chalk">{entry.remaining}</span>
          <span className="text-dim">left</span>
          {entry.dropToNext !== null && (
            <span className="text-dim">
              · then <span className="tabular">{entry.dropToNext.toFixed(1)}</span> drop
            </span>
          )}
        </span>
      ))}
    </div>
  );
}
