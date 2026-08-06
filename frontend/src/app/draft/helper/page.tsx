'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import axios from 'axios';

export default function LiveDraftStartPage() {
  const router = useRouter();
  const [draftId, setDraftId] = useState('');
  const [pickSlot, setPickSlot] = useState('1');
  const [isProcessing, setIsProcessing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleStartLiveDraft = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsProcessing(true);
    setError(null);
    try {
      const response = await axios.post('http://localhost:8000/draft/helper/start', {
        pick_slot: parseInt(pickSlot),
        draft_id: draftId.trim(),
      });
      const { session_id } = response.data;
      router.push(`/draft/helper/${session_id}`);
    } catch (err) {
      console.error('Error starting live draft:', err);
      // The backend returns 400 with an "error" key when Sleeper rejects the id.
      const detail = axios.isAxiosError(err) ? err.response?.data?.error : null;
      setError(detail ?? 'Failed to start live draft. Check that the Sleeper draft ID is correct.');
      setIsProcessing(false);
    }
  };

  return (
    <div style={{ fontFamily: 'sans-serif', maxWidth: '750px', margin: '50px auto', padding: '20px', border: '1px solid #ccc', borderRadius: '8px', boxShadow: '0 2px 4px rgba(0,0,0,0.1)' }}>
      <h1 style={{ textAlign: 'center', color: '#333' }}>Live Draft Helper</h1>

      {isProcessing && (
        <div style={{ textAlign: 'center', marginTop: '20px', fontSize: '1.2em', color: '#1c872b' }}>
          Connecting to Sleeper and building the big board, please wait...
        </div>
      )}

      {error && (
        <div style={{ textAlign: 'center', marginTop: '20px', color: 'red' }}>{error}</div>
      )}

      <form onSubmit={handleStartLiveDraft} style={{ marginTop: '30px', padding: '20px', border: '1px solid #eee', borderRadius: '8px', backgroundColor: '#f9f9f9' }}>
        <div style={{ marginBottom: '15px' }}>
          <label htmlFor="draftId" style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold', color: '#333' }}>Sleeper Draft ID:</label>
          <input
            type="text"
            id="draftId"
            value={draftId}
            onChange={(e) => setDraftId(e.target.value)}
            required
            placeholder="e.g. 1234567890123456789"
            style={{ width: '100%', padding: '8px', border: '1px solid #ddd', borderRadius: '4px', color: '#333' }}
            disabled={isProcessing}
          />
          <p style={{ fontSize: '0.85em', color: '#666', marginTop: '5px' }}>
            Found in your Sleeper draft URL: sleeper.com/draft/nfl/<strong>&lt;draft id&gt;</strong>
          </p>
        </div>
        <div style={{ marginBottom: '15px' }}>
          <label htmlFor="pickSlot" style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold', color: '#333' }}>Your Pick Slot (1-based):</label>
          <input
            type="number"
            id="pickSlot"
            value={pickSlot}
            onChange={(e) => setPickSlot(e.target.value)}
            min="1"
            required
            style={{ width: '100%', padding: '8px', border: '1px solid #ddd', borderRadius: '4px', color: '#333' }}
            disabled={isProcessing}
          />
        </div>
        <p style={{ fontSize: '0.85em', color: '#666', marginBottom: '15px' }}>
          Team count, rounds, scoring format and draft order are read from the Sleeper draft itself.
        </p>
        <button
          type="submit"
          style={{ width: '100%', padding: '10px', fontSize: '16px', backgroundColor: '#1c872b', color: 'white', border: 'none', borderRadius: '5px', cursor: 'pointer' }}
          disabled={isProcessing}
        >
          Start Live Draft
        </button>
        <button
          type="button"
          onClick={() => router.push('/draft')}
          style={{ width: '100%', padding: '10px', fontSize: '16px', backgroundColor: '#ccc', color: '#333', border: 'none', borderRadius: '5px', cursor: 'pointer', marginTop: '10px' }}
          disabled={isProcessing}
        >
          Back
        </button>
      </form>
    </div>
  );
}
