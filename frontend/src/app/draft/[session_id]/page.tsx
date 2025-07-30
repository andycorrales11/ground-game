'use client';

import { useEffect, useState, useCallback } from 'react';
import { useParams } from 'next/navigation';
import axios from 'axios';

interface DraftState {
  session_id: string;
  current_pick_num: number;
  is_user_turn: boolean;
  on_clock_team: { type: string; roster_id?: string; team_index?: number };
  available_players: any[];
  drafted_players_count: number;
  total_picks: number;
  status: string;
}

export default function DraftPage() {
  const { session_id } = useParams();
  const [draftState, setDraftState] = useState<DraftState | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [playerToPick, setPlayerToPick] = useState('');
  const [positionFilter, setPositionFilter] = useState('ALL'); // New state for position filter
  const [sortBy, setSortBy] = useState('ADP'); // New state for sorting
  const [isProcessing, setIsProcessing] = useState(false); // New state for processing indicator

  const fetchDraftState = useCallback(async () => {
    if (!session_id) return;
    setLoading(true);
    setError(null);
    try {
      const params = {
        position_filter: positionFilter === 'ALL' ? undefined : positionFilter,
        sort_by: sortBy,
      };
      const response = await axios.get<DraftState>(`http://localhost:8000/draft/${session_id}/state`, { params });
      setDraftState(response.data);

    } catch (err) {
      console.error('Error fetching draft state:', err);
      setError('Failed to load draft state.');
    } finally {
      setLoading(false);
    }
  }, [session_id, positionFilter, sortBy]); // Add filters to dependencies

  useEffect(() => {
    fetchDraftState();
  }, [fetchDraftState]);

  const handleMakePick = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!session_id || !playerToPick || isProcessing) return; // Prevent multiple submissions

    setIsProcessing(true); // Set processing to true
    try {
      await axios.post(`http://localhost:8000/draft/${session_id}/pick`, {
        player_name: playerToPick,
      });
      setPlayerToPick('');
      fetchDraftState(); // Refresh state after pick
    } catch (err) {
      console.error('Error making pick:', err);
      setError('Failed to make pick. Player might be unavailable or name is incorrect.');
    } finally {
      setIsProcessing(false); // Set processing to false
    }
  };

  const handleSimulateNextPick = async () => {
    if (!session_id || isProcessing) return; // Prevent multiple submissions

    setIsProcessing(true); // Set processing to true
    try {
      await axios.post(`http://localhost:8000/draft/${session_id}/simulate-pick`);
      fetchDraftState(); // Refresh state after CPU pick
    } catch (err) {
      console.error('Error simulating pick:', err);
      setError('Failed to simulate pick.');
    } finally {
      setIsProcessing(false); // Set processing to false
    }
  };

  if (loading) {
    return <div style={{ textAlign: 'center', marginTop: '50px' }}>Loading draft...</div>;
  }

  if (error) {
    return <div style={{ textAlign: 'center', marginTop: '50px', color: 'red' }}>Error: {error}</div>;
  }

  if (!draftState) {
    return <div style={{ textAlign: 'center', marginTop: '50px' }}>No draft state found.</div>;
  }

  const { current_pick_num, is_user_turn, on_clock_team, available_players, drafted_players_count, total_picks, status } = draftState;

  return (
    <div style={{ fontFamily: 'sans-serif', maxWidth: '900px', margin: '50px auto', padding: '20px', border: '1px solid #ccc', borderRadius: '8px', boxShadow: '0 2px 4px rgba(0,0,0,0.1)' }}>
      <h1 style={{ textAlign: 'center', color: '#333' }}>Draft in Progress (Session ID: {session_id})</h1>
      <p style={{ textAlign: 'center', fontSize: '1.1em', marginBottom: '20px' }}>
        Pick {current_pick_num} of {total_picks} | Drafted: {drafted_players_count}
      </p>

      <div style={{ marginBottom: '20px', display: 'flex', gap: '10px', justifyContent: 'center' }}>
        <label htmlFor="positionFilter" style={{ fontWeight: 'bold' }}>Filter by Position:</label>
        <select
          id="positionFilter"
          value={positionFilter}
          onChange={(e) => setPositionFilter(e.target.value)}
          style={{ padding: '5px', borderRadius: '4px' }}
          disabled={isProcessing} // Disable while processing
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
          disabled={isProcessing} // Disable while processing
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
            <h2 style={{ color: '#0070f3', textAlign: 'center' }}>It's YOUR Turn!</h2>
          ) : (
            <h2 style={{ color: '#555', textAlign: 'center' }}>
              {on_clock_team.type === 'cpu' ? `CPU (Team ${on_clock_team.team_index !== undefined ? on_clock_team.team_index + 1 : on_clock_team.roster_id})` : `Team ${on_clock_team.roster_id}`} is on the clock.
            </h2>
          )}

          {isProcessing && <p style={{ textAlign: 'center', color: '#0070f3', fontWeight: 'bold' }}>Processing pick, please wait...</p>}

          {is_user_turn && (
            <form onSubmit={handleMakePick} style={{ display: 'flex', gap: '10px', marginTop: '15px' }}>
              <input
                type="text"
                value={playerToPick}
                onChange={(e) => setPlayerToPick(e.target.value)}
                placeholder="Enter player name to draft"
                required
                style={{ flexGrow: 1, padding: '8px', border: '1px solid #ddd', borderRadius: '4px' }}
                disabled={isProcessing} // Disable while processing
              />
              <button type="submit" style={{ padding: '8px 15px', backgroundColor: '#0070f3', color: 'white', border: 'none', borderRadius: '5px', cursor: 'pointer' }}
                disabled={isProcessing} // Disable while processing
              >
                Draft Player
              </button>
            </form>
          )}

          {!is_user_turn && on_clock_team.type === 'cpu' && (
            <div style={{ textAlign: 'center', marginTop: '15px' }}>
              <button onClick={handleSimulateNextPick} style={{ padding: '10px 20px', backgroundColor: '#ff9900', color: 'white', border: 'none', borderRadius: '5px', cursor: 'pointer' }}
                disabled={isProcessing} // Disable while processing
              >
                Simulate Next Pick
              </button>
            </div>
          )}
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
                <td style={{ padding: '8px' }}>{player.ADP?.toFixed(1) || 'N/A'}</td>
                <td style={{ padding: '8px' }}>{player.VORP?.toFixed(1) || 'N/A'}</td>
                <td style={{ padding: '8px' }}>{player.VONA?.toFixed(1) || 'N/A'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
