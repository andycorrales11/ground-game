import { render, screen } from '@testing-library/react';

import type { KeeperPick } from '@/lib/types';

import KeeperPanel from '../KeeperPanel';

/*
  The panel exists to explain the room's own numbering: a keeper draft opens on
  pick 4 and jumps from 20 to 25, which reads as a bug until you can see the four
  players already spoken for.

  The labelling claim is the one worth pinning. Picks are round and *seat*, the
  way the keeper file is written, which is deliberately not how Sleeper labels
  them -- Sleeper counts position within the round, so seat 1's second-rounder
  shows there as 2.12.
*/

const KEEPERS: KeeperPick[] = [
  { round: 1, pick: 10, overall: 10, player: 'Jahmyr Gibbs', manager: 'Adrian', is_user: false },
  { round: 5, pick: 10, overall: 58, player: 'Caleb Williams', manager: 'Andy', is_user: true },
  { round: 2, pick: 1, overall: 13, player: 'Puka Nacua', manager: null, is_user: false },
];

describe('KeeperPanel', () => {
  it('renders nothing for a league without keepers', () => {
    const { container } = render(<KeeperPanel keepers={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('labels a pick by round and seat', () => {
    render(<KeeperPanel keepers={KEEPERS} />);

    // Seat 10 in round 5, not the 58th selection and not Sleeper's 5.03.
    expect(screen.getByText('5.10')).toBeInTheDocument();
    expect(screen.getByText('2.01')).toBeInTheDocument();
  });

  it('names your own keepers as yours', () => {
    render(<KeeperPanel keepers={KEEPERS} />);

    expect(screen.getByText('You')).toBeInTheDocument();
    expect(screen.getByText('Adrian')).toBeInTheDocument();
  });

  it('counts how many are yours', () => {
    render(<KeeperPanel keepers={KEEPERS} />);
    expect(screen.getByText(/1 yours · 3/)).toBeInTheDocument();
  });

  it('falls back to a dash when the league never named its managers', () => {
    render(<KeeperPanel keepers={[KEEPERS[2]]} />);
    expect(screen.getByText('—')).toBeInTheDocument();
  });
});
