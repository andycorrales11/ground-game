/*
  An em dash means "no data", everywhere, without exception.

  This matters more than it looks. A null VORP is a player nobody projected; a
  VORP of 0.0 is a player who is exactly replacement level. Printing the first
  as "0.0" would put every unprojected kicker level with a real bench decision,
  which is the same mistake that once sorted the board into nothing but kickers.
*/
const NO_DATA = '—';

export function num(value: number | null | undefined, digits = 1): string {
  return typeof value === 'number' && Number.isFinite(value) ? value.toFixed(digits) : NO_DATA;
}

/** For quantities where the sign is the point, like VONA. */
export function signed(value: number | null | undefined, digits = 1): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) return NO_DATA;
  return `${value >= 0 ? '+' : ''}${value.toFixed(digits)}`;
}

export function integer(value: number | null | undefined): string {
  return typeof value === 'number' && Number.isFinite(value) ? String(Math.round(value)) : NO_DATA;
}
