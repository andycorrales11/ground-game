'use client';

import { useId, useState } from 'react';

import {
  DEFAULT_ROSTER,
  ROSTER_FIELDS,
  SCORING_GROUPS,
  hasStartingSlot,
  receptionsFor,
  scoringForFormat,
  type RosterCounts,
  type ScoringSettings,
} from '@/lib/league';

import { controlClass } from './FormControls';

/*
  Scoring and lineup, for the two setup forms.

  Both sections are **opt-in**, and that is a correctness requirement rather than
  a tidiness one. A live draft reads its scoring format from Sleeper; if this
  form always sent a scoring table, a standard-scoring league would silently be
  drafted on whatever preset the form happened to be showing. Off means "say
  nothing and let the backend decide", which is the only safe default when the
  backend knows more than the form does.

  When a section is on, the whole object goes -- so what is on screen is exactly
  what the board is built from.
*/

interface Props {
  /** Seeds the reception values. On the live page this component owns it. */
  presetFormat: string;
  /** Provided only where the page has no scoring select of its own. */
  onPresetFormatChange?: (format: string) => void;

  scoring: ScoringSettings | null;
  onScoringChange: (scoring: ScoringSettings | null) => void;

  roster: RosterCounts | null;
  onRosterChange: (roster: RosterCounts | null) => void;

  disabled?: boolean;
}

function NumberField({
  label,
  hint,
  value,
  onChange,
  disabled,
  step,
  min,
}: {
  label: string;
  hint?: string;
  value: number;
  onChange: (value: number) => void;
  disabled?: boolean;
  step?: string;
  min?: string;
}) {
  const id = useId();

  return (
    <div>
      <label
        htmlFor={id}
        className="font-display mb-1 block text-[11px] font-semibold uppercase tracking-[0.12em] text-dim"
      >
        {label}
      </label>
      <input
        id={id}
        type="number"
        step={step}
        min={min}
        value={value}
        disabled={disabled}
        onChange={(event) => {
          /*
            An empty input is 0, not NaN. Clearing a field to retype it would
            otherwise put NaN into the payload, which serialises to null and is
            rejected by the backend as a non-number.
          */
          const parsed = Number.parseFloat(event.target.value);
          onChange(Number.isFinite(parsed) ? parsed : 0);
        }}
        className={`${controlClass} tabular px-2 py-1.5`}
      />
      {hint && <p className="mt-1 text-[11px] text-dim">{hint}</p>}
    </div>
  );
}

function SectionToggle({
  label,
  hint,
  checked,
  onChange,
  disabled,
}: {
  label: string;
  hint: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
}) {
  const id = useId();

  return (
    <div className="flex items-start gap-2.5">
      <input
        id={id}
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(event) => onChange(event.target.checked)}
        className="mt-0.5 h-3.5 w-3.5 shrink-0 accent-chalk"
      />
      <div>
        <label
          htmlFor={id}
          className="font-display block text-xs font-semibold uppercase tracking-[0.14em] text-chalk"
        >
          {label}
        </label>
        <p className="mt-1 text-xs text-dim">{hint}</p>
      </div>
    </div>
  );
}

export default function LeagueSettings({
  presetFormat,
  onPresetFormatChange,
  scoring,
  onScoringChange,
  roster,
  onRosterChange,
  disabled,
}: Props) {
  const [open, setOpen] = useState(false);

  const customScoring = scoring !== null;
  const customRoster = roster !== null;
  const customCount = (customScoring ? 1 : 0) + (customRoster ? 1 : 0);

  const setPresetFormat = (format: string) => {
    onPresetFormatChange?.(format);
    // A format decides one thing about a scoring table: what a catch is worth.
    // Re-seed those three and leave every value the user has set alone.
    if (scoring) onScoringChange({ ...scoring, ...receptionsFor(format) });
  };

  return (
    <div className="mt-5 border-t border-line pt-4">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="font-display flex w-full items-center justify-between text-xs font-semibold uppercase tracking-[0.16em] text-dim transition-colors hover:text-chalk"
      >
        <span>Scoring &amp; lineup</span>
        <span className="tabular text-[11px] normal-case tracking-normal">
          {customCount > 0 ? (
            <span className="text-chalk">
              {customCount === 2 ? 'both customised' : customScoring ? 'scoring customised' : 'lineup customised'}
            </span>
          ) : (
            'league defaults'
          )}
          <span aria-hidden="true" className="ml-2">
            {open ? '−' : '+'}
          </span>
        </span>
      </button>

      {open && (
        <div className="mt-4 space-y-5">
          {/* --- Lineup --- */}
          <div>
            <SectionToggle
              label="Custom lineup"
              hint="Starting slots. Changes what counts as replacement level, so it moves VORP at every position."
              checked={customRoster}
              disabled={disabled}
              onChange={(checked) => onRosterChange(checked ? { ...DEFAULT_ROSTER } : null)}
            />

            {roster && (
              <>
                <div className="mt-3 grid grid-cols-4 gap-x-3 gap-y-3">
                  {ROSTER_FIELDS.map((field) => (
                    <NumberField
                      key={field.key}
                      label={field.label}
                      hint={field.hint}
                      min="0"
                      step="1"
                      value={roster[field.key]}
                      disabled={disabled}
                      onChange={(value) =>
                        onRosterChange({ ...roster, [field.key]: Math.max(0, Math.round(value)) })
                      }
                    />
                  ))}
                </div>

                {!hasStartingSlot(roster) && (
                  <p role="alert" className="mt-2 text-xs text-chalk">
                    A lineup needs at least one starting slot.
                  </p>
                )}

                <button
                  type="button"
                  onClick={() => onRosterChange({ ...DEFAULT_ROSTER })}
                  disabled={disabled}
                  className="font-display mt-3 text-[11px] uppercase tracking-[0.14em] text-dim transition-colors hover:text-chalk"
                >
                  Reset lineup
                </button>
              </>
            )}
          </div>

          {/* --- Scoring --- */}
          <div className="border-t border-line pt-4">
            <SectionToggle
              label="Custom scoring"
              hint="Points per unit of production. Projections are recomputed from these, so six-point passing touchdowns or a tight-end premium reorder the board."
              checked={customScoring}
              disabled={disabled}
              onChange={(checked) =>
                onScoringChange(checked ? scoringForFormat(presetFormat) : null)
              }
            />

            {scoring && (
              <>
                {onPresetFormatChange && (
                  <div className="mt-3 max-w-[12rem]">
                    <label
                      htmlFor="scoringPreset"
                      className="font-display mb-1 block text-[11px] font-semibold uppercase tracking-[0.12em] text-dim"
                    >
                      Start from
                    </label>
                    <select
                      id="scoringPreset"
                      value={presetFormat}
                      disabled={disabled}
                      onChange={(event) => setPresetFormat(event.target.value)}
                      className={`${controlClass} px-2 py-1.5`}
                    >
                      <option value="STD">Standard</option>
                      <option value="HalfPPR">Half-PPR</option>
                      <option value="PPR">PPR</option>
                    </select>
                  </div>
                )}

                {SCORING_GROUPS.map((group) => (
                  <div key={group.title} className="mt-4">
                    <h4 className="font-display mb-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-dim">
                      {group.title}
                    </h4>
                    <div className="grid grid-cols-3 gap-x-3 gap-y-3">
                      {group.fields.map((field) => (
                        <NumberField
                          key={field.key}
                          label={field.label}
                          step="any"
                          value={scoring[field.key]}
                          disabled={disabled}
                          onChange={(value) => onScoringChange({ ...scoring, [field.key]: value })}
                        />
                      ))}
                    </div>
                  </div>
                ))}

                <p className="mt-3 text-xs text-dim">
                  Per unit — 0.04 a pass yard is one point per 25. Kickers and
                  defenses are not projected from these; they keep their stored
                  projection.
                </p>

                <button
                  type="button"
                  onClick={() => onScoringChange(scoringForFormat(presetFormat))}
                  disabled={disabled}
                  className="font-display mt-3 text-[11px] uppercase tracking-[0.14em] text-dim transition-colors hover:text-chalk"
                >
                  Reset scoring
                </button>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
