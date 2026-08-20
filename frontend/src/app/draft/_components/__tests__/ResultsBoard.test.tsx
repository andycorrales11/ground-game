import { render, screen, waitFor } from '@testing-library/react';

import { fetchResults } from '@/lib/api';
import type { DraftResults } from '@/lib/types';

import ResultsBoard from '../ResultsBoard';

jest.mock('@/lib/api', () => ({
  fetchResults: jest.fn(),
  errorMessage: (_err: unknown, fallback: string) => fallback,
}));

const mockFetch = fetchResults as jest.MockedFunction<typeof fetchResults>;

function results(overrides: Partial<DraftResults> = {}): DraftResults {
  return {
    session_id: 's1',
    status: 'completed',
    current_pick_num: 180,
    total_picks: 180,
    rosters_are_partial: false,
    teams: [
      {
        team_index: 8,
        name: 'Andy',
        is_user: true,
        picks_made: 15,
        keepers: ['Lamar Jackson'],
        bye_conflicts: {},
        roster: [
          { slot: 'QB1', player: 'Lamar Jackson', pos: 'QB', bye: 13 },
          { slot: 'RB1', player: 'Jonathan Taylor', pos: 'RB', bye: 13 },
          { slot: 'BN1', player: null, pos: null, bye: null },
        ],
      },
      {
        team_index: 6,
        name: 'Janson',
        is_user: false,
        picks_made: 17,
        keepers: [],
        bye_conflicts: {},
        roster: [{ slot: 'QB1', player: 'Justin Herbert', pos: 'QB', bye: 5 }],
      },
    ],
    ...overrides,
  };
}

describe('ResultsBoard', () => {
  beforeEach(() => {
    mockFetch.mockReset();
    mockFetch.mockResolvedValue(results());
  });

  it('shows every team, named the way the league names them', async () => {
    render(<ResultsBoard mode="simulation" sessionId="s1" refreshKey={0} onClose={jest.fn()} />);

    // Not "Team 9" and "Team 7" -- the point of carrying manager names through.
    expect(await screen.findByRole('heading', { name: /Andy/ })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Janson' })).toBeInTheDocument();
  });

  it('marks kept players, which were never on the board', async () => {
    render(<ResultsBoard mode="simulation" sessionId="s1" refreshKey={0} onClose={jest.fn()} />);

    const kept = await screen.findByTitle('Kept, not drafted');
    expect(kept).toBeInTheDocument();
    // One keeper on Andy's roster, not one per player.
    expect(screen.getAllByTitle('Kept, not drafted')).toHaveLength(1);
  });

  it('says so when only your roster is filled in', async () => {
    mockFetch.mockResolvedValue(results({ rosters_are_partial: true }));
    render(<ResultsBoard mode="live" sessionId="s1" refreshKey={0} onClose={jest.fn()} />);

    expect(await screen.findByText(/Sleeper owns the rosters/)).toBeInTheDocument();
  });

  it('reports the pick it is showing while the draft is still running', async () => {
    mockFetch.mockResolvedValue(results({ status: 'in_progress', current_pick_num: 42 }));
    render(<ResultsBoard mode="simulation" sessionId="s1" refreshKey={0} onClose={jest.fn()} />);

    expect(await screen.findByText(/Through pick 42/)).toBeInTheDocument();
  });

  it('refetches when the board moves, so an open table does not go stale', async () => {
    const { rerender } = render(
      <ResultsBoard mode="simulation" sessionId="s1" refreshKey={0} onClose={jest.fn()} />,
    );
    await waitFor(() => expect(mockFetch).toHaveBeenCalledTimes(1));

    rerender(
      <ResultsBoard mode="simulation" sessionId="s1" refreshKey={1} onClose={jest.fn()} />,
    );
    await waitFor(() => expect(mockFetch).toHaveBeenCalledTimes(2));
  });

  it('surfaces a failure rather than showing an empty table', async () => {
    mockFetch.mockRejectedValue(new Error('nope'));
    render(<ResultsBoard mode="simulation" sessionId="s1" refreshKey={0} onClose={jest.fn()} />);

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Could not load the draft results.',
    );
  });
});
