import type { ReactNode } from 'react';

interface Props {
  title: string;
  /** Optional right-aligned detail in the header, e.g. a count or a timestamp. */
  aside?: ReactNode;
  children: ReactNode;
}

/** A sidebar card. One border, one label, no ornament. */
export default function Panel({ title, aside, children }: Props) {
  return (
    <section className="border border-line bg-deck">
      <header className="flex items-baseline justify-between gap-3 border-b border-line px-3 py-2">
        <h2 className="font-display text-xs font-semibold uppercase tracking-[0.18em] text-dim">
          {title}
        </h2>
        {aside}
      </header>
      {children}
    </section>
  );
}
