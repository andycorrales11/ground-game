import { render, screen } from '@testing-library/react';

import type { RosterSlot } from '@/lib/types';

import RosterPanel from '../RosterPanel';

const ROSTER: RosterSlot[] = [
  { slot: 'QB', player: 'Josh Allen', pos: 'QB', bye: 7 },
  { slot: 'RB1', player: 'Bijan Robinson', pos: 'RB', bye: 8 },
  { slot: 'RB2', player: 'Breece Hall', pos: 'RB', bye: 8 },
  { slot: 'WR1', player: 'Puka Nacua', pos: 'WR', bye: 8 },
  { slot: 'WR2', player: null, pos: null, bye: null },
];

describe('RosterPanel', () => {
  it('renders every slot, filled or not', () => {
    render(<RosterPanel roster={ROSTER} byeConflicts={{}} />);

    expect(screen.getByText('Josh Allen')).toBeInTheDocument();
    expect(screen.getByText('WR2')).toBeInTheDocument();
    expect(screen.getByText('empty')).toBeInTheDocument();
  });

  it('counts how much of the roster is filled', () => {
    render(<RosterPanel roster={ROSTER} byeConflicts={{}} />);

    expect(screen.getByText('4 / 5')).toBeInTheDocument();
  });

  it('says so explicitly when there are no conflicts', () => {
    render(<RosterPanel roster={ROSTER} byeConflicts={{}} />);

    // "No warning" and "not checked" look identical if this stays silent.
    expect(screen.getByText(/No week takes out more than one/i)).toBeInTheDocument();
  });

  it('lists a conflicting week with its players', () => {
    render(
      <RosterPanel
        roster={ROSTER}
        byeConflicts={{ '8': ['Bijan Robinson', 'Breece Hall', 'Puka Nacua'] }}
      />,
    );

    expect(screen.getByText('Week 8')).toBeInTheDocument();
    expect(
      screen.getByText(/3 out — Bijan Robinson, Breece Hall, Puka Nacua/),
    ).toBeInTheDocument();
  });

  it('flags each rostered player who is out that week', () => {
    render(
      <RosterPanel roster={ROSTER} byeConflicts={{ '8': ['Bijan Robinson', 'Breece Hall'] }} />,
    );

    // The three players on bye in week 8, each carrying the same explanation.
    const flagged = screen.getAllByTitle('2 of your players are out in week 8');
    expect(flagged).toHaveLength(3);
  });

  it('escalates the hatch from two players to three', () => {
    const { container: mild } = render(
      <RosterPanel roster={ROSTER} byeConflicts={{ '8': ['Bijan Robinson', 'Breece Hall'] }} />,
    );
    expect(mild.querySelectorAll('.hazard-mild').length).toBeGreaterThan(0);
    expect(mild.querySelectorAll('.hazard-severe')).toHaveLength(0);

    const { container: severe } = render(
      <RosterPanel
        roster={ROSTER}
        byeConflicts={{ '8': ['Bijan Robinson', 'Breece Hall', 'Puka Nacua'] }}
      />,
    );
    expect(severe.querySelectorAll('.hazard-severe').length).toBeGreaterThan(0);
  });

  it('renders nothing when there is no roster to show', () => {
    // Live mode does not populate opponent rosters -- Sleeper owns them.
    const { container } = render(<RosterPanel roster={[]} byeConflicts={{}} />);

    expect(container).toBeEmptyDOMElement();
  });
});
