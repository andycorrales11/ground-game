import { fireEvent, render, screen, waitFor } from '@testing-library/react';

import { startSimulation } from '@/lib/api';
import { DEFAULT_ROSTER, scoringForFormat } from '@/lib/league';

import StartPage from '../page';

jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: jest.fn() }),
}));

jest.mock('@/lib/api', () => ({
  startSimulation: jest.fn(),
  errorMessage: (_err: unknown, fallback: string) => fallback,
}));

const mockStart = startSimulation as jest.MockedFunction<typeof startSimulation>;

function openForm() {
  render(<StartPage />);
  fireEvent.click(screen.getByRole('button', { name: /mock draft/i }));
}

function openSettings() {
  fireEvent.click(screen.getByRole('button', { name: /scoring & lineup/i }));
}

function submit() {
  fireEvent.click(screen.getByRole('button', { name: /start mock draft/i }));
}

describe('StartPage', () => {
  beforeEach(() => {
    mockStart.mockReset();
    mockStart.mockResolvedValue('session-1');
  });

  it('omits scoring and roster entirely when nothing is customised', async () => {
    openForm();
    submit();

    await waitFor(() => expect(mockStart).toHaveBeenCalled());

    const payload = mockStart.mock.calls[0][0];
    // Absent, not sent as defaults: the backend's own preset is the source of
    // truth for anything the form has no opinion about.
    expect(payload).not.toHaveProperty('scoring');
    expect(payload).not.toHaveProperty('roster');
    expect(payload).toMatchObject({ pick_slot: 1, teams: 12, rounds: 15, format: 'PPR' });
  });

  it('sends the whole scoring table once it is customised', async () => {
    openForm();
    openSettings();
    fireEvent.click(screen.getByLabelText('Custom scoring'));
    fireEvent.change(screen.getByLabelText('Pass TD'), { target: { value: '6' } });
    submit();

    await waitFor(() => expect(mockStart).toHaveBeenCalled());

    // The whole object, not a diff -- what is on screen is what the board uses.
    expect(mockStart.mock.calls[0][0].scoring).toEqual({
      ...scoringForFormat('PPR'),
      pass_tds: 6,
    });
  });

  it('sends a superflex lineup', async () => {
    openForm();
    openSettings();
    fireEvent.click(screen.getByLabelText('Custom lineup'));
    fireEvent.change(screen.getByLabelText('SUPERFLEX'), { target: { value: '1' } });
    submit();

    await waitFor(() => expect(mockStart).toHaveBeenCalled());

    expect(mockStart.mock.calls[0][0].roster).toEqual({ ...DEFAULT_ROSTER, superflex: 1 });
  });

  it('re-seeds catch values when the scoring format changes', async () => {
    openForm();
    openSettings();
    fireEvent.click(screen.getByLabelText('Custom scoring'));
    fireEvent.change(screen.getByLabelText('Scoring'), { target: { value: 'STD' } });
    submit();

    await waitFor(() => expect(mockStart).toHaveBeenCalled());

    const payload = mockStart.mock.calls[0][0];
    expect(payload.format).toBe('STD');
    expect(payload.scoring).toEqual(scoringForFormat('STD'));
  });

  it('will not start a draft with a lineup that starts nobody', () => {
    openForm();
    openSettings();
    fireEvent.click(screen.getByLabelText('Custom lineup'));
    for (const label of ['QB', 'RB', 'WR', 'TE', 'FLEX', 'SUPERFLEX', 'K', 'D/ST']) {
      fireEvent.change(screen.getByLabelText(label), { target: { value: '0' } });
    }

    // Caught here rather than as a 400 after the round trip.
    expect(screen.getByRole('button', { name: /start mock draft/i })).toBeDisabled();
  });
});
