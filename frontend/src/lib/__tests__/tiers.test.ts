import { assignTiers, scarcityByPosition, tiersAreInReadingOrder } from '../tiers';
import type { Player } from '../types';

function player(name: string, pos: string, vorp: number | null): Player {
  return {
    normalized_name: name,
    display_name: name,
    pos,
    team: 'ATL',
    bye: 5,
    ADP: 10,
    // Tiers are cut on VORP alone, so the projection is only here to satisfy
    // the shape -- if it ever starts mattering, these tests should say so.
    PTS: vorp === null ? null : 140 + vorp,
    VORP: vorp,
    VONA: 0,
  };
}

describe('assignTiers', () => {
  it('breaks a tier at a clear gap in VORP', () => {
    const players = [
      player('a', 'RB', 100),
      player('b', 'RB', 98),
      player('c', 'RB', 96),
      player('d', 'RB', 60),
      player('e', 'RB', 58),
    ];

    const tiers = assignTiers(players);

    expect(tiers.get('a')?.tier).toBe(1);
    expect(tiers.get('c')?.tier).toBe(1);
    expect(tiers.get('d')?.tier).toBe(2);
    expect(tiers.get('e')?.tier).toBe(2);
  });

  it('reports the cost of waiting on the last player of a tier', () => {
    const players = [
      player('a', 'RB', 100),
      player('b', 'RB', 98),
      player('c', 'RB', 96),
      player('d', 'RB', 60),
    ];

    const tiers = assignTiers(players);

    expect(tiers.get('c')).toMatchObject({ isLastOfTier: true, dropToNext: 36 });
    // Everyone inside a tier reports no drop -- the cliff belongs to its edge.
    expect(tiers.get('a')).toMatchObject({ isLastOfTier: false, dropToNext: null });
    // And the last player overall has nothing to drop to.
    expect(tiers.get('d')).toMatchObject({ isLastOfTier: false, dropToNext: null });
  });

  it('leaves an evenly spread position as a single tier', () => {
    const players = [player('a', 'WR', 50), player('b', 'WR', 50), player('c', 'WR', 50)];

    const tiers = assignTiers(players);

    expect([...tiers.values()].every((info) => info.tier === 1)).toBe(true);
  });

  it('does not splinter a position whose gaps are all small', () => {
    // Gaps of 1, 1 and 4. The largest is comfortably past 1.8x the median, so
    // without the absolute floor this would report two tiers over a spread of
    // six points -- a distinction worth nothing on a draft board.
    const players = [
      player('a', 'TE', 50),
      player('b', 'TE', 49),
      player('c', 'TE', 48),
      player('d', 'TE', 44),
    ];

    const tiers = assignTiers(players);

    expect([...tiers.values()].every((info) => info.tier === 1)).toBe(true);
  });

  it('finds a break that a mean-based threshold would miss', () => {
    // Gaps of 10, 10, 10 and 20. The mean gap is 12.5, so a mean-based
    // threshold sits at 22.5 and the 20-point cliff clears nothing -- the big
    // gap drags the average past itself. The median is unmoved at 10.
    const players = [
      player('a', 'WR', 100),
      player('b', 'WR', 90),
      player('c', 'WR', 80),
      player('d', 'WR', 70),
      player('e', 'WR', 50),
    ];

    const tiers = assignTiers(players);

    expect(tiers.get('d')?.tier).toBe(1);
    expect(tiers.get('e')?.tier).toBe(2);
  });

  it('tiers each position independently', () => {
    const players = [
      player('rb1', 'RB', 100),
      player('rb2', 'RB', 98),
      player('rb3', 'RB', 96),
      player('rb4', 'RB', 40),
      player('wr1', 'WR', 90),
      player('wr2', 'WR', 88),
      player('wr3', 'WR', 86),
      player('wr4', 'WR', 84),
    ];

    const tiers = assignTiers(players);

    expect(tiers.get('rb4')?.tier).toBe(2);
    // The RB cliff must not push the WRs down with it: they are evenly spread
    // and belong in one tier however severe the drop-off at running back is.
    expect(tiers.get('wr4')?.tier).toBe(1);
  });

  it('never splits a position with only two players', () => {
    // A single gap is its own median, so the threshold is 1.8x the only
    // evidence there is and nothing can clear it. That is the intended
    // behaviour rather than a limitation to work around: two players give no
    // basis for calling the space between them unusual.
    const tiers = assignTiers([player('a', 'RB', 100), player('b', 'RB', 40)]);

    expect(tiers.get('a')?.tier).toBe(1);
    expect(tiers.get('b')?.tier).toBe(1);
  });

  it('omits players with no projection rather than tiering them at zero', () => {
    const players = [player('a', 'K', 20), player('b', 'K', null)];

    const tiers = assignTiers(players);

    expect(tiers.has('a')).toBe(true);
    expect(tiers.has('b')).toBe(false);
  });

  it('handles a position with a single player', () => {
    const tiers = assignTiers([player('a', 'DEF', 12)]);

    expect(tiers.get('a')).toMatchObject({ tier: 1, isLastOfTier: false, dropToNext: null });
  });

  it('returns nothing for an empty board', () => {
    expect(assignTiers([]).size).toBe(0);
  });
});

describe('tiersAreInReadingOrder', () => {
  const players = [
    player('a', 'RB', 100),
    player('b', 'RB', 98),
    player('c', 'RB', 60),
    player('d', 'RB', 58),
  ];
  const tiers = assignTiers(players);

  it('accepts a list whose tiers never go backwards', () => {
    expect(tiersAreInReadingOrder(players, tiers)).toBe(true);
  });

  it('rejects a list that revisits an earlier tier', () => {
    // What sorting by ADP does: a tier-2 player can sit above a tier-1 one, and
    // a cliff drawn between them would point at nothing.
    const byAdp = [players[0], players[2], players[1], players[3]];

    expect(tiersAreInReadingOrder(byAdp, tiers)).toBe(false);
  });

  it('ignores players it has no tier for', () => {
    const withUnprojected = [players[0], player('x', 'RB', null), players[1]];

    expect(tiersAreInReadingOrder(withUnprojected, tiers)).toBe(true);
  });
});

describe('scarcityByPosition', () => {
  it('counts only the best tier still on the board, thinnest position first', () => {
    const players = [
      player('rb1', 'RB', 100),
      player('rb2', 'RB', 98),
      player('rb3', 'RB', 50), // tier 2 -- past the cliff, so not counted
      player('wr1', 'WR', 90),
      player('wr2', 'WR', 89),
      player('wr3', 'WR', 88),
    ];

    const scarcity = scarcityByPosition(players, assignTiers(players));

    expect(scarcity.map((entry) => entry.pos)).toEqual(['RB', 'WR']);
    expect(scarcity[0]).toMatchObject({ pos: 'RB', remaining: 2, dropToNext: 48 });
    expect(scarcity[1]).toMatchObject({ pos: 'WR', remaining: 3, dropToNext: null });
  });

  it('skips positions with nothing projected', () => {
    const players = [player('k1', 'K', null)];

    expect(scarcityByPosition(players, assignTiers(players))).toEqual([]);
  });
});
