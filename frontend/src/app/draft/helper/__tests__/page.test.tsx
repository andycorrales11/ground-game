import { fireEvent, render, screen, waitFor } from '@testing-library/react';

import { startLiveDraft } from '@/lib/api';
import { DEFAULT_ROSTER, scoringForFormat } from '@/lib/league';

import LiveDraftStartPage from '../page';

jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: jest.fn() }),
}));

jest.mock('@/lib/api', () => ({
  startLiveDraft: jest.fn(),
  errorMessage: (_err: unknown, fallback: string) => fallback,
}));

const mockStart = startLiveDraft as jest.MockedFunction<typeof startLiveDraft>;

function fillAndSubmit() {
  fireEvent.change(screen.getByLabelText(/sleeper draft id/i), {
    target: { value: '1234567890123456789' },
  });
  fireEvent.click(screen.getByRole('button', { name: /start live draft/i }));
}

function openSettings() {
  fireEvent.click(screen.getByRole('button', { name: /scoring & lineup/i }));
}

describe('LiveDraftStartPage', () => {
  beforeEach(() => {
    mockStart.mockReset();
    mockStart.mockResolvedValue('session-1');
  });

  it('sends no overrides at all when nothing is customised', async () => {
    /*
      The important one. Sleeper reports the league's scoring format, and the
      backend uses it. If this page sent a scoring table anyway, a standard
      league would be drafted on whatever preset the form was showing.
    */
    render(<LiveDraftStartPage />);
    fillAndSubmit();

    await waitFor(() => expect(mockStart).toHaveBeenCalled());

    expect(mockStart).toHaveBeenCalledWith('1234567890123456789', 1, {});
  });

  it('sends scoring only once the user asks for it', async () => {
    render(<LiveDraftStartPage />);
    openSettings();
    fireEvent.click(screen.getByLabelText('Custom scoring'));
    fireEvent.change(screen.getByLabelText('Catch (TE)'), { target: { value: '1.5' } });
    fillAndSubmit();

    await waitFor(() => expect(mockStart).toHaveBeenCalled());

    expect(mockStart.mock.calls[0][2]).toEqual({
      scoring: { ...scoringForFormat('PPR'), receptions_te: 1.5 },
    });
  });

  it('has its own preset selector, since there is no scoring field on this page', async () => {
    render(<LiveDraftStartPage />);
    openSettings();
    fireEvent.click(screen.getByLabelText('Custom scoring'));
    fireEvent.change(screen.getByLabelText('Start from'), { target: { value: 'STD' } });
    fillAndSubmit();

    await waitFor(() => expect(mockStart).toHaveBeenCalled());

    expect(mockStart.mock.calls[0][2]).toEqual({ scoring: scoringForFormat('STD') });
  });

  it('sends a lineup without a scoring table, and vice versa', async () => {
    render(<LiveDraftStartPage />);
    openSettings();
    fireEvent.click(screen.getByLabelText('Custom lineup'));
    fireEvent.change(screen.getByLabelText('SUPERFLEX'), { target: { value: '1' } });
    fillAndSubmit();

    await waitFor(() => expect(mockStart).toHaveBeenCalled());

    const overrides = mockStart.mock.calls[0][2];
    expect(overrides).toEqual({ roster: { ...DEFAULT_ROSTER, superflex: 1 } });
    expect(overrides).not.toHaveProperty('scoring');
  });

  it('still says which settings Sleeper supplies', () => {
    render(<LiveDraftStartPage />);

    expect(
      screen.getByText(/teams, rounds, draft order and the scoring format are read from the sleeper draft/i),
    ).toBeInTheDocument();
  });
});
