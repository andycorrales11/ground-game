import axios from 'axios';

import type { DraftMode, DraftState, LivePick } from './types';

/*
  127.0.0.1, not localhost, and deliberately so.

  On Windows `localhost` resolves AAAA-first while uvicorn's default listener is
  IPv4-only, so every request pays the IPv6 connection failure before falling
  back. Measured on this machine: ~2048ms per request against ~2.6ms straight to
  127.0.0.1. During a live draft the board refreshes on every poll, so that is
  the difference between a usable tool and an unusable one. See issue #27.

  NEXT_PUBLIC_API_URL overrides it for any deployment where the API is not local.
*/
export const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://127.0.0.1:8000';

/*
  Generous, because it has to be. Refreshing the board on your turn runs a real
  forward simulation of every CPU pick until your next one, five times over. It
  is the slowest thing the app does and it is not optional.
*/
const REQUEST_TIMEOUT_MS = 60_000;

const client = axios.create({ baseURL: API_BASE, timeout: REQUEST_TIMEOUT_MS });

/** Simulation and live are parallel route families over the same engine. */
const ROUTE_BASE: Record<DraftMode, string> = {
  simulation: '/draft/simulation',
  live: '/draft/helper',
};

/*
  The backend reports failure two different ways: most routes raise
  HTTPException, which FastAPI renders as {detail}, while the /start routes
  return a JSONResponse carrying {error}. Read both, so no caller has to know
  which one it hit.
*/
export function errorMessage(err: unknown, fallback: string): string {
  if (axios.isAxiosError(err)) {
    const data = err.response?.data as { detail?: string; error?: string } | undefined;
    return data?.detail ?? data?.error ?? fallback;
  }
  return fallback;
}

export interface BoardQuery {
  positionFilter: string;
  sortBy: string;
}

export async function fetchDraftState(
  mode: DraftMode,
  sessionId: string,
  query: BoardQuery,
): Promise<DraftState> {
  const { data } = await client.get<DraftState>(`${ROUTE_BASE[mode]}/${sessionId}/state`, {
    params: {
      // 'ALL' is the absence of a filter, not a filter value the backend knows.
      position_filter: query.positionFilter === 'ALL' ? undefined : query.positionFilter,
      sort_by: query.sortBy,
    },
  });
  return data;
}

/*
  The name goes through normalize_name on the way in, so the display name off a
  board row is exactly what this wants -- no client-side normalisation, and no
  need for the caller to know the roster stores a different form.
*/
export async function submitPick(
  mode: DraftMode,
  sessionId: string,
  playerName: string,
): Promise<void> {
  await client.post(`${ROUTE_BASE[mode]}/${sessionId}/pick`, { player_name: playerName });
}

/** Simulation only. The backend rejects this for any session with a draft_id. */
export async function simulateNextPick(sessionId: string): Promise<void> {
  await client.post(`${ROUTE_BASE.simulation}/${sessionId}/simulate-pick`);
}

/** Live only. Returns just the picks that are new since the last call. */
export async function pollLiveDraft(sessionId: string): Promise<LivePick[]> {
  const { data } = await client.get<{ new_picks?: LivePick[] }>(
    `${ROUTE_BASE.live}/${sessionId}/poll-live`,
  );
  return data.new_picks ?? [];
}

export interface SimulationSettings {
  pick_slot: number;
  teams: number;
  rounds: number;
  format: string;
  order: string;
}

/** Returns the new session id. */
export async function startSimulation(settings: SimulationSettings): Promise<string> {
  const { data } = await client.post<{ session_id: string }>(
    `${ROUTE_BASE.simulation}/start`,
    settings,
  );
  return data.session_id;
}

/**
 * Returns the new session id. Team count, rounds, scoring and order all come
 * from the Sleeper draft itself, so this takes only what Sleeper cannot tell us.
 */
export async function startLiveDraft(draftId: string, pickSlot: number): Promise<string> {
  const { data } = await client.post<{ session_id: string }>(`${ROUTE_BASE.live}/start`, {
    draft_id: draftId,
    pick_slot: pickSlot,
  });
  return data.session_id;
}
