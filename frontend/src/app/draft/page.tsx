'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import axios from 'axios'; // Import axios

export default function StartPage() {
  const router = useRouter();
  const [mode, setMode] = useState<null | 'simulation' | 'live'>(null);
  const [isProcessing, setIsProcessing] = useState(false); // New state for processing indicator

  // State for Live Draft Helper
  const [liveDraftId, setLiveDraftId] = useState('');
  const [livePickSlot, setLivePickSlot] = useState('1');

  // State for Simulation
  const [simPickSlot, setSimPickSlot] = useState('1');
  const [simTeams, setSimTeams] = useState('12');
  const [simRounds, setSimRounds] = useState('15');
  const [simFormat, setSimFormat] = useState('STD');
  const [simOrder, setSimOrder] = useState('snake');

  const handleStartLiveDraft = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsProcessing(true); // Set processing to true
    try {
      const response = await axios.post('http://localhost:8000/draft/helper/start', {
        pick_slot: parseInt(livePickSlot),
        draft_id: liveDraftId,
      });
      const { session_id } = response.data;
      router.push(`/draft/simulation/${session_id}`);
    } catch (error) {
      console.error('Error starting live draft:', error);
      alert('Failed to start live draft. Please check the console for details.');
    } finally {
      setIsProcessing(false); // Set processing to false
    }
  };

  const handleStartSimulation = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsProcessing(true); // Set processing to true
    try {
      const response = await axios.post('http://localhost:8000/draft/simulation/start', {
        pick_slot: parseInt(simPickSlot),
        teams: parseInt(simTeams),
        rounds: parseInt(simRounds),
        format: simFormat,
        order: simOrder,
      });
      const { session_id } = response.data;
      router.push(`/draft/simulation/${session_id}`);
    } catch (error) {
      console.error('Error starting simulation:', error);
      alert('Failed to start simulation. Please check the console for details.');
    } finally {
      setIsProcessing(false); // Set processing to false
    }
  };

  return (
    <div style={{ fontFamily: 'sans-serif', maxWidth: '750px', margin: '50px auto', padding: '20px', border: '1px solid #ccc', borderRadius: '8px', boxShadow: '0 2px 4px rgba(0,0,0,0.1)' }}>
      <h1 style={{ textAlign: 'center', color: '#333' }}>Ground Game Draft Assistant</h1>

      {isProcessing && (
        <div style={{ textAlign: 'center', marginTop: '20px', fontSize: '1.2em', color: '#0070f3' }}>
          Starting draft, please wait...
        </div>
      )}

      {!mode && (
        <div style={{ display: 'flex', justifyContent: 'space-around', marginTop: '30px' }}>
          <button
            onClick={() => setMode('simulation')}
            style={{ padding: '12px 25px', fontSize: '16px', cursor: 'pointer', backgroundColor: '#0070f3', color: 'white', border: 'none', borderRadius: '5px' }}
            disabled={isProcessing} // Disable while processing
          >
            Start Simulation
          </button>
          <button
            onClick={() => setMode('live')}
            style={{ padding: '12px 25px', fontSize: '16px', cursor: 'pointer', backgroundColor: '#1c872b', color: 'white', border: 'none', borderRadius: '5px' }}
            disabled={isProcessing} // Disable while processing
          >
            Start Live Draft Helper
          </button>
        </div>
      )}

      {mode === 'live' && (
        <form onSubmit={handleStartLiveDraft} style={{ marginTop: '30px', padding: '20px', border: '1px solid #eee', borderRadius: '8px', backgroundColor: '#f9f9f9' }}>
          <h2 style={{ textAlign: 'center', color: '#222' }}>Live Draft Helper</h2>
          <div style={{ marginBottom: '15px' }}>
            <label htmlFor="liveDraftId" style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold', color: '#333' }}>Sleeper Draft ID:</label>
            <input
              type="text"
              id="liveDraftId"
              value={liveDraftId}
              onChange={(e) => setLiveDraftId(e.target.value)}
              required
              style={{ width: '100%', padding: '8px', border: '1px solid #ddd', borderRadius: '4px', color: '#333' }}
              disabled={isProcessing} // Disable while processing
            />
          </div>
          <div style={{ marginBottom: '15px' }}>
            <label htmlFor="livePickSlot" style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold', color: '#333' }}>Your Pick Slot (1-based):</label>
            <input
              type="number"
              id="livePickSlot"
              value={livePickSlot}
              onChange={(e) => setLivePickSlot(e.target.value)}
              min="1"
              required
              style={{ width: '100%', padding: '8px', border: '1px solid #ddd', borderRadius: '4px', color: '#333'  
               }}
              disabled={isProcessing} // Disable while processing
            />
          </div>
          <button type="submit" style={{ width: '100%', padding: '10px', fontSize: '16px', backgroundColor: '#1c872b', color: 'white', border: 'none', borderRadius: '5px', cursor: 'pointer' }}
            disabled={isProcessing} // Disable while processing
          >
            Start Live Draft
          </button>
          <button type="button" onClick={() => setMode(null)} style={{ width: '100%', padding: '10px', fontSize: '16px', backgroundColor: '#ccc', color: '#333', border: 'none', borderRadius: '5px', cursor: 'pointer', marginTop: '10px' }}
            disabled={isProcessing} // Disable while processing
          >
            Back
          </button>
        </form>
      )}

      {mode === 'simulation' && (
        <form onSubmit={handleStartSimulation} style={{ marginTop: '30px', padding: '20px', border: '1px solid #eee', borderRadius: '8px', backgroundColor: '#f9f9f9' }}>
          <h2 style={{ textAlign: 'center', color: '#222' }}>Draft Simulation</h2>
          <div style={{ marginBottom: '15px' }}>
            <label htmlFor="simPickSlot" style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold', color: '#333' }}>Your Pick Slot (1-based):</label>
            <input
              type="number"
              id="simPickSlot"
              value={simPickSlot}
              onChange={(e) => setSimPickSlot(e.target.value)}
              min="1"
              required
              style={{ width: '100%', padding: '8px', border: '1px solid #ddd', borderRadius: '4px' }}
              disabled={isProcessing} // Disable while processing
            />
          </div>
          <div style={{ marginBottom: '15px' }}>
            <label htmlFor="simTeams" style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold', color: '#333' }}>Number of Teams:</label>
            <input
              type="number"
              id="simTeams"
              value={simTeams}
              onChange={(e) => setSimTeams(e.target.value)}
              min="2"
              required
              style={{ width: '100%', padding: '8px', border: '1px solid #ddd', borderRadius: '4px' }}
              disabled={isProcessing} // Disable while processing
            />
          </div>
          <div style={{ marginBottom: '15px' }}>
            <label htmlFor="simRounds" style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold', color: '#333' }}>Number of Rounds:</label>
            <input
              type="number"
              id="simRounds"
              value={simRounds}
              onChange={(e) => setSimRounds(e.target.value)}
              min="1"
              required
              style={{ width: '100%', padding: '8px', border: '1px solid #ddd', borderRadius: '4px' }}
              disabled={isProcessing} // Disable while processing
            />
          </div>
          <div style={{ marginBottom: '15px' }}>
            <label htmlFor="simFormat" style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold', color: '#333' }}>Scoring Format:</label>
            <select
              id="simFormat"
              value={simFormat}
              onChange={(e) => setSimFormat(e.target.value)}
              style={{ width: '100%', padding: '8px', border: '1px solid #ddd', borderRadius: '4px' }}
              disabled={isProcessing} // Disable while processing
            >
              <option value="STD">Standard</option>
              <option value="HALF_PPR">Half-PPR</option>
              <option value="PPR">PPR</option>
            </select>
          </div>
          <div style={{ marginBottom: '15px' }}>
            <label htmlFor="simOrder" style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold', color: '#333' }}>Draft Order:</label>
            <select
              id="simOrder"
              value={simOrder}
              onChange={(e) => setSimOrder(e.target.value)}
              style={{ width: '100%', padding: '8px', border: '1px solid #ddd', borderRadius: '4px' }}
              disabled={isProcessing} // Disable while processing
            >
              <option value="snake">Snake</option>
              <option value="normal">Normal</option>
            </select>
          </div>
          <button type="submit" style={{ width: '100%', padding: '10px', fontSize: '16px', backgroundColor: '#0070f3', color: 'white', border: 'none', borderRadius: '5px', cursor: 'pointer' }}
            disabled={isProcessing} // Disable while processing
          >
            Start Simulation
          </button>
          <button type="button" onClick={() => setMode(null)} style={{ width: '100%', padding: '10px', fontSize: '16px', backgroundColor: '#ccc', color: '#333', border: 'none', borderRadius: '5px', cursor: 'pointer', marginTop: '10px' }}
            disabled={isProcessing} // Disable while processing
          >
            Back
          </button>
        </form>
      )}
    </div>
  );
}
