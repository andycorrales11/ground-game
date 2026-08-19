import { fireEvent, render, screen } from '@testing-library/react';

import { assignTiers } from '@/lib/tiers';
import type { Player } from '@/lib/types';

import PlayerBoard from '../PlayerBoard';

function player(
  name: string,
  pos: string,
  vorp: number | null,
  overrides: Partial<Player> = {},
): Player {
  return {
    normalized_name: name.toLowerCase().replace(/\s+/g, '_'),
    display_name: name,
    pos,
    team: 'ATL',
    bye: 5,
    ADP: 12.4,
    // Projected total points, which VORP is measured down from -- so a fixture
    // that gave the two unrelated numbers would not resemble a real board.
    PTS: vorp === null ? null : 140 + vorp,
    VORP: vorp,
    VONA: 8.2,
    ...overrides,
  };
}

// A clean cliff: three close together, then a 36-point drop.
const PLAYERS = [
  player('Bijan Robinson', 'RB', 100),
  player('Jahmyr Gibbs', 'RB', 98),
  player('Breece Hall', 'RB', 96),
  player('Kenneth Walker', 'RB', 60),
];

const TIERS = assignTiers(PLAYERS);

function renderBoard(overrides: Partial<React.ComponentProps<typeof PlayerBoard>> = {}) {
  const props = {
    players: PLAYERS,
    tiers: TIERS,
    showCliffs: true,
    sortBy: 'VORP',
    selectedName: null,
    onSelect: jest.fn(),
    onConfirm: jest.fn(),
    ...overrides,
  };
  return { ...render(<PlayerBoard {...props} />), props };
}

describe('PlayerBoard', () => {
  it('renders a row per player', () => {
    renderBoard();

    expect(screen.getByText('Bijan Robinson')).toBeInTheDocument();
    expect(screen.getByText('Kenneth Walker')).toBeInTheDocument();
  });

  it('draws a cliff where the tier ends', () => {
    renderBoard();

    const cliffs = screen.getAllByRole('separator');
    expect(cliffs).toHaveLength(1);
    expect(cliffs[0]).toHaveTextContent(/Tier 1 ends/);
    // The number is the whole point of the marker: what waiting actually costs.
    expect(cliffs[0]).toHaveTextContent(/36\.0/);
  });

  it('draws no cliff when the tiers would not read down the page in order', () => {
    renderBoard({ showCliffs: false });

    expect(screen.queryByRole('separator')).not.toBeInTheDocument();
  });

  it('selects a player when their row is clicked', () => {
    const { props } = renderBoard();

    fireEvent.click(screen.getByText('Jahmyr Gibbs'));

    expect(props.onSelect).toHaveBeenCalledWith('jahmyr_gibbs');
  });

  it('drafts a player on double click', () => {
    const { props } = renderBoard();

    fireEvent.doubleClick(screen.getByText('Breece Hall'));

    expect(props.onConfirm).toHaveBeenCalledWith(
      expect.objectContaining({ display_name: 'Breece Hall' }),
    );
  });

  it('marks the selected row for assistive technology', () => {
    renderBoard({ selectedName: 'breece_hall' });

    expect(screen.getByRole('row', { selected: true })).toHaveTextContent('Breece Hall');
  });

  it('shows the season projection each player is valued from', () => {
    renderBoard();

    // 140 + VORP, per the fixture. The column has to print the projection itself,
    // not repeat VORP: the gap between the two is the argument for taking a tight
    // end over a wide receiver who outscores him.
    expect(screen.getByText('240.0')).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: 'Proj' })).toBeInTheDocument();
  });

  it('shows an em dash rather than a zero for a missing metric', () => {
    renderBoard({
      players: [player('Unprojected Guy', 'WR', null, { ADP: null, VONA: null })],
      tiers: new Map(),
    });

    // Four metric columns, all unknown. A zero here would read as replacement
    // level, which is a real and very different thing.
    expect(screen.getAllByText('—')).toHaveLength(4);
  });

  it('prints VONA whoever is on the clock', () => {
    renderBoard();

    // VONA is the span between now and your next pick, and that span exists off
    // your turn too -- it is longer, which is the point. The column used to be
    // greyed out and dashed for every pick that was not yours.
    expect(screen.getAllByText('+8.2')).toHaveLength(PLAYERS.length);
  });

  it('invites an action when nothing matches the filter', () => {
    renderBoard({ players: [] });

    expect(screen.getByText(/Nothing on the board matches/i)).toBeInTheDocument();
    expect(screen.getByText(/Clear the filter/i)).toBeInTheDocument();
  });

  it('marks the sorted column so it can be read at a glance', () => {
    renderBoard({ sortBy: 'VONA' });

    expect(screen.getByRole('columnheader', { name: 'VONA' })).toHaveAttribute(
      'aria-sort',
      'descending',
    );
    expect(screen.getByRole('columnheader', { name: 'ADP' })).toHaveAttribute(
      'aria-sort',
      'none',
    );
  });
});
