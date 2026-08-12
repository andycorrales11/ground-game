/*
  Two of your players sharing a bye is a nuisance you plan around; three or more
  is a week you probably lose. The difference is carried by hatch density and
  weight rather than by colour, because colour on this page means position -- and
  an amber warning sitting next to an amber TE would make both of them ambiguous.
*/

export function severityClass(count: number): string {
  return count >= 3 ? 'hazard-severe' : 'hazard-mild';
}

interface Props {
  byeConflicts: Record<string, string[]>;
}

export default function ByeConflicts({ byeConflicts }: Props) {
  const weeks = Object.keys(byeConflicts ?? {})
    .map(Number)
    .filter((week) => Number.isFinite(week))
    .sort((a, b) => a - b);

  if (weeks.length === 0) {
    // Worth saying out loud: "no warning" and "not checked yet" look identical otherwise.
    return (
      <p className="border-t border-line px-3 py-2 text-xs text-dim">
        No week takes out more than one of your players.
      </p>
    );
  }

  return (
    <div className="border-t border-line px-3 py-2">
      <h3 className="font-display mb-1.5 text-[11px] font-semibold uppercase tracking-[0.16em] text-dim">
        Bye conflicts
      </h3>
      <ul className="space-y-1.5">
        {weeks.map((week) => {
          const players = byeConflicts[String(week)];
          const severe = players.length >= 3;

          return (
            <li key={week} className="flex items-baseline gap-2 text-xs">
              <span
                className={`${severityClass(players.length)} inline-block h-2.5 w-5 shrink-0 translate-y-0.5`}
                aria-hidden="true"
              />
              <span className={severe ? 'font-semibold text-chalk' : 'text-chalk/80'}>
                Week {week}
              </span>
              <span className="text-dim">
                {players.length} out — {players.join(', ')}
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
