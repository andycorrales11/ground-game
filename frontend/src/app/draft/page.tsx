'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';

import { errorMessage, startSimulation } from '@/lib/api';

import {
  Field,
  controlClass,
  primaryButtonClass,
  quietButtonClass,
} from './_components/FormControls';

export default function StartPage() {
  const router = useRouter();
  const [showForm, setShowForm] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [pickSlot, setPickSlot] = useState('1');
  const [teams, setTeams] = useState('12');
  const [rounds, setRounds] = useState('15');
  const [format, setFormat] = useState('PPR');
  const [order, setOrder] = useState('snake');

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setIsProcessing(true);
    setError(null);
    try {
      const sessionId = await startSimulation({
        pick_slot: Number.parseInt(pickSlot, 10),
        teams: Number.parseInt(teams, 10),
        rounds: Number.parseInt(rounds, 10),
        format,
        order,
      });
      router.push(`/draft/simulation/${sessionId}`);
    } catch (err) {
      // Replaces an alert(), which stopped the page dead and said nothing useful.
      setError(errorMessage(err, 'Could not start the draft. Is the backend running?'));
      setIsProcessing(false);
    }
  };

  return (
    <main className="mx-auto min-h-screen max-w-2xl px-5 py-16 sm:py-24">
      <h1 className="font-display text-5xl font-bold uppercase tracking-[0.14em] text-chalk sm:text-6xl">
        Ground Game
      </h1>
      {/*
        The thesis, and the one thing this board does that a printed cheat sheet
        cannot: it plays the rest of the round out before you pick.
      */}
      <p className="font-display mt-2 text-xl uppercase tracking-[0.08em] text-dim sm:text-2xl">
        Know what waiting costs
      </p>
      <p className="mt-6 max-w-lg text-sm leading-relaxed text-dim">
        A value-based draft board. It simulates the rest of the round before your
        pick, so you can see who will still be on the board when it comes back
        around — and where the drop-off is if they are not.
      </p>

      {error && (
        <p role="alert" className="mt-8 border border-line bg-deck px-3 py-2 text-sm text-chalk">
          <span className="hazard-severe mr-2 inline-block h-3 w-3 translate-y-0.5" />
          {error}
        </p>
      )}

      {!showForm ? (
        <div className="mt-12 grid gap-3 sm:grid-cols-2">
          <button
            type="button"
            onClick={() => setShowForm(true)}
            className="group border border-line bg-deck p-5 text-left transition-colors hover:border-chalk"
          >
            <span className="font-display block text-sm font-semibold uppercase tracking-[0.16em] text-chalk">
              Mock draft
            </span>
            <span className="mt-1.5 block text-xs text-dim">
              Draft against CPU opponents. You set the league up.
            </span>
          </button>

          <button
            type="button"
            onClick={() => router.push('/draft/helper')}
            className="group border border-line bg-deck p-5 text-left transition-colors hover:border-chalk"
          >
            <span className="font-display block text-sm font-semibold uppercase tracking-[0.16em] text-chalk">
              Live draft
            </span>
            <span className="mt-1.5 block text-xs text-dim">
              Follow a real Sleeper draft and get advice as it runs.
            </span>
          </button>
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="mt-12 border border-line bg-deck p-5">
          <h2 className="font-display mb-5 text-sm font-semibold uppercase tracking-[0.16em] text-dim">
            League setup
          </h2>

          <div className="grid gap-x-4 sm:grid-cols-2">
            <Field label="Your pick slot" htmlFor="pickSlot">
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

            <Field label="Teams" htmlFor="teams">
              <input
                id="teams"
                type="number"
                min="2"
                required
                value={teams}
                onChange={(event) => setTeams(event.target.value)}
                disabled={isProcessing}
                className={controlClass}
              />
            </Field>

            <Field label="Rounds" htmlFor="rounds">
              <input
                id="rounds"
                type="number"
                min="1"
                required
                value={rounds}
                onChange={(event) => setRounds(event.target.value)}
                disabled={isProcessing}
                className={controlClass}
              />
            </Field>

            <Field label="Scoring" htmlFor="format">
              <select
                id="format"
                value={format}
                onChange={(event) => setFormat(event.target.value)}
                disabled={isProcessing}
                className={controlClass}
              >
                {/* These values are the canonical forms the backend accepts verbatim. */}
                <option value="STD">Standard</option>
                <option value="HalfPPR">Half-PPR</option>
                <option value="PPR">PPR</option>
              </select>
            </Field>

            <Field label="Draft order" htmlFor="order">
              <select
                id="order"
                value={order}
                onChange={(event) => setOrder(event.target.value)}
                disabled={isProcessing}
                className={controlClass}
              >
                <option value="snake">Snake</option>
                <option value="normal">Straight</option>
              </select>
            </Field>
          </div>

          <div className="mt-3 space-y-2">
            <button type="submit" disabled={isProcessing} className={primaryButtonClass}>
              {isProcessing ? 'Building the board' : 'Start mock draft'}
            </button>
            <button
              type="button"
              onClick={() => setShowForm(false)}
              disabled={isProcessing}
              className={quietButtonClass}
            >
              Back
            </button>
          </div>
        </form>
      )}
    </main>
  );
}
