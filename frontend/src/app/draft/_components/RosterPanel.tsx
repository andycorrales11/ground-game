'use client';

import { RosterSlot } from './types';

// Two players sharing a bye is a nuisance you plan around; three or more is a week
// you probably lose. They are coloured differently so the distinction survives a
// glance mid-draft.
const MILD = '#8a6d00';
const SEVERE = '#a11';

function severityColor(count: number): string {
  return count >= 3 ? SEVERE : MILD;
}

interface Props {
  roster: RosterSlot[];
  byeConflicts: Record<string, string[]>;
}

export default function RosterPanel({ roster, byeConflicts }: Props) {
  if (!roster || roster.length === 0) return null;

  const conflictWeeks = Object.keys(byeConflicts ?? {})
    .map(Number)
    .sort((a, b) => a - b);

  const countForWeek = (bye: number | null): number =>
    bye === null ? 0 : byeConflicts?.[String(bye)]?.length ?? 0;

  return (
    <div style={{ marginTop: '30px' }}>
      <h3 style={{ color: '#333' }}>Your Roster</h3>

      {conflictWeeks.length > 0 && (
        <div
          style={{
            marginBottom: '10px',
            padding: '10px',
            border: '1px solid #e0c000',
            borderRadius: '6px',
            backgroundColor: '#fffbe6',
          }}
        >
          <strong style={{ color: '#333' }}>Bye week conflicts:</strong>
          <ul style={{ margin: '6px 0 0', paddingLeft: '20px' }}>
            {conflictWeeks.map((week) => {
              const players = byeConflicts[String(week)];
              return (
                <li key={week} style={{ color: severityColor(players.length) }}>
                  <strong>Week {week}</strong> — {players.length} players out
                </li>
              );
            })}
          </ul>
        </div>
      )}

      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
        <thead>
          <tr style={{ backgroundColor: '#464444ff' }}>
            <th style={{ padding: '8px', borderBottom: '1px solid #ddd', textAlign: 'left' }}>Slot</th>
            <th style={{ padding: '8px', borderBottom: '1px solid #ddd', textAlign: 'left' }}>Player</th>
            <th style={{ padding: '8px', borderBottom: '1px solid #ddd', textAlign: 'left' }}>Pos</th>
            <th style={{ padding: '8px', borderBottom: '1px solid #ddd', textAlign: 'left' }}>Bye</th>
          </tr>
        </thead>
        <tbody>
          {roster.map((slot) => {
            const clash = countForWeek(slot.bye);
            return (
              <tr key={slot.slot} style={{ borderBottom: '1px solid #eee' }}>
                <td style={{ padding: '8px', fontWeight: 'bold' }}>{slot.slot}</td>
                <td style={{ padding: '8px', color: slot.player ? undefined : '#999' }}>
                  {slot.player ?? 'empty'}
                </td>
                <td style={{ padding: '8px' }}>{slot.pos ?? ''}</td>
                <td
                  style={{
                    padding: '8px',
                    color: clash > 0 ? severityColor(clash) : undefined,
                    fontWeight: clash > 0 ? 'bold' : undefined,
                  }}
                  title={clash > 0 ? `${clash} of your players are out in week ${slot.bye}` : undefined}
                >
                  {slot.bye ?? (slot.player ? '—' : '')}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
