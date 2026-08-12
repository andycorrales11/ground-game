import type { ReactNode } from 'react';

/** One control style, so the two setup forms cannot drift apart again. */
export const controlClass =
  'w-full border border-line bg-pitch px-3 py-2 text-sm text-chalk placeholder:text-dim focus:border-chalk focus:outline-none';

export const primaryButtonClass =
  'font-display w-full bg-chalk px-4 py-2.5 text-sm font-semibold uppercase tracking-[0.14em] text-pitch transition-opacity disabled:cursor-not-allowed disabled:opacity-40';

export const quietButtonClass =
  'font-display w-full border border-line px-4 py-2.5 text-sm font-semibold uppercase tracking-[0.14em] text-dim transition-colors hover:text-chalk disabled:opacity-40';

interface FieldProps {
  label: string;
  htmlFor: string;
  /** Shown under the control. For guidance, never for restating the label. */
  hint?: ReactNode;
  children: ReactNode;
}

export function Field({ label, htmlFor, hint, children }: FieldProps) {
  return (
    <div className="mb-4">
      <label
        htmlFor={htmlFor}
        className="font-display mb-1.5 block text-xs font-semibold uppercase tracking-[0.16em] text-dim"
      >
        {label}
      </label>
      {children}
      {hint && <p className="mt-1.5 text-xs text-dim">{hint}</p>}
    </div>
  );
}
