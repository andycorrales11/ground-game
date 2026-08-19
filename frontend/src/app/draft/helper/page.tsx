'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';

import { errorMessage, startLiveDraft } from '@/lib/api';
import { hasStartingSlot, type RosterCounts, type ScoringSettings } from '@/lib/league';

import {
  Field,
  controlClass,
  primaryButtonClass,
  quietButtonClass,
} from '../_components/FormControls';
import LeagueSettings from '../_components/LeagueSettings';

export default function LiveDraftStartPage() {
  const router = useRouter();
  const [draftId, setDraftId] = useState('');
  const [pickSlot, setPickSlot] = useState('1');
  const [isProcessing, setIsProcessing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /*
    Both null unless the user says otherwise, and here that matters more than it
    does in a mock draft: Sleeper reports the league's scoring format, and
    sending a scoring table anyway would override it with whatever preset this
    form happened to be showing. Only a deliberate customisation is sent.

    `presetFormat` seeds the values when the user does turn scoring on. It is
    the form's own starting point, not a claim about the Sleeper league -- the
    ADP column still comes from the format Sleeper reports.
  */
  const [scoring, setScoring] = useState<ScoringSettings | null>(null);
  const [roster, setRoster] = useState<RosterCounts | null>(null);
  const [presetFormat, setPresetFormat] = useState('PPR');

  const lineupIsEmpty = roster !== null && !hasStartingSlot(roster);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setIsProcessing(true);
    setError(null);
    try {
      const sessionId = await startLiveDraft(draftId.trim(), Number.parseInt(pickSlot, 10), {
        ...(scoring ? { scoring } : {}),
        ...(roster ? { roster } : {}),
      });
      router.push(`/draft/helper/${sessionId}`);
    } catch (err) {
      setError(
        errorMessage(err, 'Could not start the live draft. Check that the Sleeper draft ID is right.'),
      );
      setIsProcessing(false);
    }
  };

  return (
    <main className="mx-auto min-h-screen max-w-2xl px-5 py-16 sm:py-24">
      <h1 className="font-display text-4xl font-bold uppercase tracking-[0.14em] text-chalk sm:text-5xl">
        Live draft
      </h1>
      <p className="mt-4 max-w-lg text-sm leading-relaxed text-dim">
        Ground Game follows the draft in Sleeper and keeps the board in step with
        it. You still make your picks in Sleeper — this tells you which one to make.
      </p>

      {error && (
        <p role="alert" className="mt-8 border border-line bg-deck px-3 py-2 text-sm text-chalk">
          <span className="hazard-severe mr-2 inline-block h-3 w-3 translate-y-0.5" />
          {error}
        </p>
      )}

      <form onSubmit={handleSubmit} className="mt-10 border border-line bg-deck p-5">
        <Field
          label="Sleeper draft ID"
          htmlFor="draftId"
          hint={
            <>
              The last part of the draft URL: sleeper.com/draft/nfl/
              <span className="text-chalk">&lt;draft id&gt;</span>
            </>
          }
        >
          <input
            id="draftId"
            type="text"
            required
            inputMode="numeric"
            placeholder="1234567890123456789"
            value={draftId}
            onChange={(event) => setDraftId(event.target.value)}
            disabled={isProcessing}
            className={`${controlClass} tabular`}
          />
        </Field>

        <Field
          label="Your pick slot"
          htmlFor="pickSlot"
          hint="Teams, rounds, draft order and the scoring format are read from the Sleeper draft."
        >
          <input
            id="pickSlot"
            type="number"
            min="1"
            required
            value={pickSlot}
            onChange={(event) => setPickSlot(event.target.value)}
            disabled={isProcessing}
            className={controlClass}
          />
        </Field>

        <LeagueSettings
          presetFormat={presetFormat}
          onPresetFormatChange={setPresetFormat}
          scoring={scoring}
          onScoringChange={setScoring}
          roster={roster}
          onRosterChange={setRoster}
          disabled={isProcessing}
        />

        <div className="mt-5 space-y-2">
          <button
            type="submit"
            disabled={isProcessing || lineupIsEmpty}
            className={primaryButtonClass}
          >
            {isProcessing ? 'Connecting to Sleeper' : 'Start live draft'}
          </button>
          <button
            type="button"
            onClick={() => router.push('/draft')}
            disabled={isProcessing}
            className={quietButtonClass}
          >
            Back
          </button>
        </div>
      </form>
    </main>
  );
}
