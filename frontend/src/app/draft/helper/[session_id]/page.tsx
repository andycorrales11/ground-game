'use client';

import { useEffect, useState, useCallback, useRef } from 'react';
import { useParams } from 'next/navigation';
import axios from 'axios';

const API = 'http://localhost:8000';

// How often to ask Sleeper for new picks. The board refresh that follows is
// expensive on your turn (VONA runs a forward simulation per candidate), so this
// is deliberately not aggressive.
const POLL_INTERVAL_MS = 8000;

interface Player {
  normalized_name: string;
  display_name: string;
  pos: string;
  team: string | null;
  ADP: number | null;
  VORP: number | null;
  VONA: number | null;
  [key: string]: string | number | null | undefined;
}

interface DraftState {
  session_id: string;
  current_pick_num: number;
  is_user_turn: boolean;
  on_clock_team: { type: string; roster_id?: string; team_index?: number };
  available_players: Player[];
  drafted_players_count: number;
  total_picks: number;
  status: string;
}

interface LivePick {
  pick_number: number;
  roster_id: string;
  player_name: string;
  position: string;
}

export default function LiveDraftPage() {
  const { session_id } = useParams();
  const [draftState, setDraftState] = useState<DraftState | null>(null);
  const [recentPicks, setRecentPicks] = useState<LivePick[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [playerToPick, setPlayerToPick] = useState('');
  const [positionFilter, setPositionFilter] = useState('ALL');
  const [sortBy, setSortBy] = useState('ADP');
  const [isProcessing, setIsProcessing] = useState(false);
  const [lastSync, setLastSync] = useState<Date | null>(null);

  // Guards against overlapping polls: a board refresh on your turn can outlast
  // the poll interval, and stacking those requests makes the page crawl.
  const inFlight = useRef(false);

  const fetchDraftState = useCallback(async () => {
    if (!session_id) return;
    try {
      const params = {
        position_filter: positionFilter === 'ALL' ? undefined : positionFilter,
        sort_by: sortBy,
      };
      const response = await axios.get<DraftState>(`${API}/draft/helper/${session_id}/state`, { params });
      setDraftState(response.data);
      setError(null);
    } catch (err) {
      console.error('Error fetching draft state:', err);
      setError('Failed to load draft state.');
    } finally {
      setLoading(false);
    }
  }, [session_id, positionFilter, sortBy]);

  // Pull any picks that have happened in the real Sleeper draft, then refresh the
  // board only when something actually changed.
  const pollSleeper = useCallback(async () => {
    if (!session_id || inFlight.current) return;
    inFlight.current = true;
    try {
      const response = await axios.get<{ new_picks?: LivePick[] }>(`${API}/draft/helper/${session_id}/poll-live`);
      setLastSync(new Date());
      const newPicks = response.data.new_picks ?? [];
      if (newPicks.length > 0) {
        setRecentPicks((prev) => [...newPicks].reverse().concat(prev).slice(0, 10));
        await fetchDraftState();
      }
    } catch (err) {
      console.error('Error polling Sleeper:', err);
    } finally {
      inFlight.current = false;
    }
  }, [session_id, fetchDraftState]);

  // Initial load, and a reload whenever the filter or sort changes.
  useEffect(() => {
    fetchDraftState();
  }, [fetchDraftState]);

  useEffect(() => {
    const id = setInterval(pollSleeper, POLL_INTERVAL_MS);
    return () => clearInterval(id);
  }, [pollSleeper]);

  const handleMakePick = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!session_id || !playerToPick || isProcessing) return;

    setIsProcessing(true);
    try {
      await axios.post(`${API}/draft/helper/${session_id}/pick`, { player_name: playerToPick });
      setPlayerToPick('');
      await fetchDraftState();
    } catch (err) {
      console.error('Error making pick:', err);
      setError('Failed to record pick. Check the player name, or wait for Sleeper to sync it.');
    } finally {
      setIsProcessing(false);
    }
  };

  const handleRefreshNow = async () => {
    setIsProcessing(true);
    await pollSleeper();
    await fetchDraftState();
    setIsProcessing(false);
  };

  if (loading) {
    return <div style={{ textAlign: 'center', marginTop: '50px' }}>Connecting to your Sleeper draft...</div>;
  }

  if (!draftState) {
    return (
      <div style={{ textAlign: 'center', marginTop: '50px', color: 'red' }}>
        {error ?? 'No draft state found.'}
      </div>
    );
  }

  const { current_pick_num, is_user_turn, on_clock_team, available_players, drafted_players_count, total_picks, status } = draftState;

  return (
    <div style={{ fontFamily: 'sans-serif', maxWidth: '900px', margin: '50px auto', padding: '20px', border: '1px solid #ccc', borderRadius: '8px', boxShadow: '0 2px 4px rgba(0,0,0,0.1)' }}>
      <h1 style={{ textAlign: 'center', color: '#333' }}>Live Draft Helper</h1>
      <p style={{ textAlign: 'center', fontSize: '1.1em', marginBottom: '5px' }}>
        Pick {current_pick_num} of {total_picks} | Drafted: {drafted_players_count}
      </p>
      <p style={{ textAlign: 'center', fontSize: '0.85em', color: '#666', marginBottom: '20px' }}>
        Syncing with Sleeper every {POLL_INTERVAL_MS / 1000}s
        {lastSync && ` — last checked ${lastSync.toLocaleTimeString()}`}
        {' · '}
        <button
          onClick={handleRefreshNow}
          disabled={isProcessing}
          style={{ background: 'none', border: 'none', color: '#0070f3', cursor: 'pointer', padding: 0, fontSize: 'inherit', textDecoration: 'underline' }}
        >
          refresh now
        </button>
      </p>

      {error && <p style={{ textAlign: 'center', color: 'red' }}>{error}</p>}

      <div style={{ marginBottom: '20px', display: 'flex', gap: '10px', justifyContent: 'center' }}>
        <label htmlFor="positionFilter" style={{ fontWeight: 'bold' }}>Filter by Position:</label>
        <select
          id="positionFilter"
          value={positionFilter}
          onChange={(e) => setPositionFilter(e.target.value)}
          style={{ padding: '5px', borderRadius: '4px' }}
          disabled={isProcessing}
        >
          <option value="ALL">All</option>
          <option value="QB">QB</option>
          <option value="RB">RB</option>
          <option value="WR">WR</option>
          <option value="TE">TE</option>
          <option value="FLEX">FLEX</option>
          <option value="K">K</option>
          <option value="DEF">DEF</option>
        </select>

        <label htmlFor="sortBy" style={{ fontWeight: 'bold', marginLeft: '20px' }}>Sort By:</label>
        <select
          id="sortBy"
          value={sortBy}
          onChange={(e) => setSortBy(e.target.value)}
          style={{ padding: '5px', borderRadius: '4px' }}
          disabled={isProcessing}
        >
          <option value="ADP">ADP</option>
          <option value="VORP">VORP</option>
          <option value="VONA">VONA</option>
        </select>
      </div>

      {status === 'completed' ? (
        <h2 style={{ textAlign: 'center', color: 'green' }}>Draft Complete!</h2>
      ) : (
        <div style={{ marginBottom: '20px', padding: '15px', border: '1px solid #ddd', borderRadius: '8px', backgroundColor: '#f9f9f9' }}>
          {is_user_turn ? (
            <h2 style={{ color: '#1c872b', textAlign: 'center' }}>It&apos;s YOUR Turn!</h2>
          ) : (
            <h2 style={{ color: '#555', textAlign: 'center' }}>
              {/* Live sessions identify teams by Sleeper roster id; fall back to the
                  slot index so this never renders as a bare "Team is on the clock". */}
              Team {on_clock_team.roster_id ?? (on_clock_team.team_index !== undefined ? on_clock_team.team_index + 1 : '?')} is on the clock.
            </h2>
          )}

          {isProcessing && <p style={{ textAlign: 'center', color: '#0070f3', fontWeight: 'bold' }}>Working, please wait...</p>}

          {is_user_turn && (
            <>
              <p style={{ textAlign: 'center', fontSize: '0.85em', color: '#666', marginTop: '10px' }}>
                Make the pick in Sleeper. It will sync here automatically, or record it below to update the board immediately.
              </p>
              <form onSubmit={handleMakePick} style={{ display: 'flex', gap: '10px', marginTop: '15px' }}>
                <input
                  type="text"
                  value={playerToPick}
                  onChange={(e) => setPlayerToPick(e.target.value)}
                  placeholder="Enter player name to record"
                  required
                  style={{ flexGrow: 1, padding: '8px', border: '1px solid #ddd', borderRadius: '4px' }}
                  disabled={isProcessing}
                />
                <button
                  type="submit"
                  style={{ padding: '8px 15px', backgroundColor: '#1c872b', color: 'white', border: 'none', borderRadius: '5px', cursor: 'pointer' }}
                  disabled={isProcessing}
                >
                  Record Pick
                </button>
              </form>
            </>
          )}
        </div>
      )}

      {recentPicks.length > 0 && (
        <div style={{ marginBottom: '20px' }}>
          <h3 style={{ color: '#333' }}>Recent Picks from Sleeper:</h3>
          <ul style={{ margin: 0, paddingLeft: '20px', color: '#555' }}>
            {recentPicks.map((pick) => (
              <li key={pick.pick_number}>
                Pick {pick.pick_number}: Team {pick.roster_id} took {pick.player_name} ({pick.position})
              </li>
            ))}
          </ul>
        </div>
      )}

      <h3 style={{ marginTop: '30px', color: '#333' }}>Available Players (Top 50):</h3>
      <div style={{ maxHeight: '400px', overflowY: 'auto', border: '1px solid #eee', borderRadius: '8px', padding: '10px' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ backgroundColor: '#464444ff' }}>
              <th style={{ padding: '8px', borderBottom: '1px solid #ddd', textAlign: 'left' }}>Name</th>
              <th style={{ padding: '8px', borderBottom: '1px solid #ddd', textAlign: 'left' }}>Pos</th>
              <th style={{ padding: '8px', borderBottom: '1px solid #ddd', textAlign: 'left' }}>Team</th>
              <th style={{ padding: '8px', borderBottom: '1px solid #ddd', textAlign: 'left' }}>ADP</th>
              <th style={{ padding: '8px', borderBottom: '1px solid #ddd', textAlign: 'left' }}>VORP</th>
              <th style={{ padding: '8px', borderBottom: '1px solid #ddd', textAlign: 'left' }}>VONA</th>
            </tr>
          </thead>
          <tbody>
            {available_players.map((player) => (
              <tr key={player.normalized_name} style={{ borderBottom: '1px solid #eee' }}>
                <td style={{ padding: '8px' }}>{player.display_name}</td>
                <td style={{ padding: '8px' }}>{player.pos}</td>
                <td style={{ padding: '8px' }}>{player.team}</td>
                <td style={{ padding: '8px' }}>{player.ADP?.toFixed(1) ?? 'N/A'}</td>
                <td style={{ padding: '8px' }}>{player.VORP?.toFixed(1) ?? 'N/A'}</td>
                <td style={{ padding: '8px' }}>{player.VONA?.toFixed(1) ?? 'N/A'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
