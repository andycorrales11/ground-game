import { fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';

import { DEFAULT_ROSTER, scoringForFormat, type RosterCounts, type ScoringSettings } from '@/lib/league';

import LeagueSettings from '../LeagueSettings';

/*
  The property under test throughout: null means "say nothing and let the backend
  decide", and it is not the same as sending the preset's values. A live draft
  takes its scoring format from Sleeper, so a form that always sent a scoring
  table would silently override it.
*/

function Harness({
  withPresetSelect = false,
  onScoring,
  onRoster,
}: {
  withPresetSelect?: boolean;
  onScoring?: (scoring: ScoringSettings | null) => void;
  onRoster?: (roster: RosterCounts | null) => void;
}) {
  const [scoring, setScoring] = useState<ScoringSettings | null>(null);
  const [roster, setRoster] = useState<RosterCounts | null>(null);
  const [format, setFormat] = useState('PPR');

  return (
    <LeagueSettings
      presetFormat={format}
      onPresetFormatChange={withPresetSelect ? setFormat : undefined}
      scoring={scoring}
      onScoringChange={(next) => {
        setScoring(next);
        onScoring?.(next);
      }}
      roster={roster}
      onRosterChange={(next) => {
        setRoster(next);
        onRoster?.(next);
      }}
    />
  );
}

function open() {
  fireEvent.click(screen.getByRole('button', { name: /scoring & lineup/i }));
}

describe('LeagueSettings', () => {
  it('starts collapsed and says the league is on defaults', () => {
    render(<Harness />);

    expect(screen.getByText('league defaults')).toBeInTheDocument();
    expect(screen.queryByLabelText('Pass TD')).not.toBeInTheDocument();
  });

  it('sends nothing until a section is turned on', () => {
    const onScoring = jest.fn();
    const onRoster = jest.fn();
    render(<Harness onScoring={onScoring} onRoster={onRoster} />);

    open();

    // Opening the section is not customising anything.
    expect(onScoring).not.toHaveBeenCalled();
    expect(onRoster).not.toHaveBeenCalled();
    expect(screen.queryByLabelText('Pass TD')).not.toBeInTheDocument();
  });

  it('seeds scoring from the preset format when switched on', () => {
    const onScoring = jest.fn();
    render(<Harness onScoring={onScoring} />);

    open();
    fireEvent.click(screen.getByLabelText('Custom scoring'));

    expect(onScoring).toHaveBeenCalledWith(scoringForFormat('PPR'));
    expect(screen.getByLabelText('Pass TD')).toHaveValue(4);
    expect(screen.getByLabelText('Catch (WR)')).toHaveValue(1);
  });

  it('switching a section back off clears it rather than leaving the values behind', () => {
    const onScoring = jest.fn();
    render(<Harness onScoring={onScoring} />);

    open();
    fireEvent.click(screen.getByLabelText('Custom scoring'));
    fireEvent.click(screen.getByLabelText('Custom scoring'));

    expect(onScoring).toHaveBeenLastCalledWith(null);
    expect(screen.queryByLabelText('Pass TD')).not.toBeInTheDocument();
  });

  it('edits one scoring value and leaves the rest of the table alone', () => {
    const onScoring = jest.fn();
    render(<Harness onScoring={onScoring} />);

    open();
    fireEvent.click(screen.getByLabelText('Custom scoring'));
    fireEvent.change(screen.getByLabelText('Pass TD'), { target: { value: '6' } });

    expect(onScoring).toHaveBeenLastCalledWith({ ...scoringForFormat('PPR'), pass_tds: 6 });
  });

  it('a cleared field reads as 0, never NaN', () => {
    // NaN serialises to null, which the backend rejects as a non-number -- so an
    // interrupted edit would fail the whole draft start.
    const onScoring = jest.fn();
    render(<Harness onScoring={onScoring} />);

    open();
    fireEvent.click(screen.getByLabelText('Custom scoring'));
    fireEvent.change(screen.getByLabelText('Interception'), { target: { value: '' } });

    expect(onScoring).toHaveBeenLastCalledWith({ ...scoringForFormat('PPR'), interceptions: 0 });
  });

  it('changing the preset re-seeds receptions and keeps other edits', () => {
    const onScoring = jest.fn();
    render(<Harness withPresetSelect onScoring={onScoring} />);

    open();
    fireEvent.click(screen.getByLabelText('Custom scoring'));
    fireEvent.change(screen.getByLabelText('Pass TD'), { target: { value: '6' } });
    fireEvent.change(screen.getByLabelText('Start from'), { target: { value: 'STD' } });

    expect(onScoring).toHaveBeenLastCalledWith({
      ...scoringForFormat('STD'),
      // The format decides what a catch is worth and nothing else, so a
      // six-point passing touchdown survives the change.
      pass_tds: 6,
    });
  });

  it('offers a superflex slot, which no preset lineup has', () => {
    const onRoster = jest.fn();
    render(<Harness onRoster={onRoster} />);

    open();
    fireEvent.click(screen.getByLabelText('Custom lineup'));

    expect(onRoster).toHaveBeenCalledWith(DEFAULT_ROSTER);
    expect(screen.getByLabelText('SUPERFLEX')).toHaveValue(0);

    fireEvent.change(screen.getByLabelText('SUPERFLEX'), { target: { value: '1' } });
    expect(onRoster).toHaveBeenLastCalledWith({ ...DEFAULT_ROSTER, superflex: 1 });
  });

  it('warns when a lineup has no starting slot at all', () => {
    render(<Harness />);

    open();
    fireEvent.click(screen.getByLabelText('Custom lineup'));
    for (const label of ['QB', 'RB', 'WR', 'TE', 'FLEX', 'SUPERFLEX', 'K', 'D/ST']) {
      fireEvent.change(screen.getByLabelText(label), { target: { value: '0' } });
    }

    expect(screen.getByRole('alert')).toHaveTextContent(/at least one starting slot/i);
  });

  it('summarises what has been customised without being opened', () => {
    render(<Harness />);

    open();
    fireEvent.click(screen.getByLabelText('Custom lineup'));
    expect(screen.getByText('lineup customised')).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText('Custom scoring'));
    expect(screen.getByText('both customised')).toBeInTheDocument();
  });
});
