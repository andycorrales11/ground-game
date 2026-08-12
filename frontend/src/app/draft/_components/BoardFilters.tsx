'use client';

import type { RefObject } from 'react';

import { BOARD_FILTERS, SORT_OPTIONS, positionStyle } from '@/lib/positions';

/*
  ALL and FLEX are not positions, so they do not get a position hue -- they take
  plain chalk instead. Giving FLEX its own colour would put a seventh meaning
  into a palette whose entire premise is that colour means position.
*/
const NEUTRAL_FILTERS = new Set<string>(['ALL', 'FLEX']);

interface Props {
  positionFilter: string;
  onPositionFilterChange: (value: string) => void;
  sortBy: string;
  onSortByChange: (value: string) => void;
  query: string;
  onQueryChange: (value: string) => void;
  queryInputRef: RefObject<HTMLInputElement | null>;
  showing: number;
}

export default function BoardFilters({
  positionFilter,
  onPositionFilterChange,
  sortBy,
  onSortByChange,
  query,
  onQueryChange,
  queryInputRef,
  showing,
}: Props) {
  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-3 border-b border-line px-3 py-2.5">
      <div className="flex flex-wrap gap-1" role="group" aria-label="Filter by position">
        {BOARD_FILTERS.map((filter) => {
          const active = filter === positionFilter;
          const activeClass = NEUTRAL_FILTERS.has(filter)
            ? 'bg-chalk text-pitch'
            : positionStyle(filter).chip;

          return (
            <button
              key={filter}
              type="button"
              onClick={() => onPositionFilterChange(filter)}
              aria-pressed={active}
              className={`font-display px-2.5 py-1 text-xs font-semibold uppercase tracking-[0.12em] transition-colors ${
                active ? activeClass : 'text-dim hover:bg-line hover:text-chalk'
              }`}
            >
              {filter}
            </button>
          );
        })}
      </div>

      <div className="flex items-center gap-1" role="group" aria-label="Sort the board">
        <span className="font-display mr-1 text-xs uppercase tracking-[0.16em] text-dim">
          Sort
        </span>
        {SORT_OPTIONS.map((option) => {
          const active = option.value === sortBy;
          return (
            <button
              key={option.value}
              type="button"
              onClick={() => onSortByChange(option.value)}
              aria-pressed={active}
              title={option.hint}
              className={`font-display px-2 py-1 text-xs font-semibold uppercase tracking-[0.12em] transition-colors ${
                active ? 'bg-chalk text-pitch' : 'text-dim hover:bg-line hover:text-chalk'
              }`}
            >
              {option.label}
            </button>
          );
        })}
      </div>

      <div className="ml-auto flex items-center gap-2">
        <label htmlFor="board-filter" className="sr-only">
          Filter the board by name
        </label>
        <input
          id="board-filter"
          ref={queryInputRef}
          type="search"
          value={query}
          onChange={(event) => onQueryChange(event.target.value)}
          /*
            "Filter", not "search", and the distinction is real: this narrows the
            rows already on the board, it does not reach past them into the full
            player pool. Calling it search would promise something it cannot do.
          */
          placeholder="Filter board   /"
          className="w-44 border border-line bg-pitch px-2.5 py-1 text-sm text-chalk placeholder:text-dim focus:border-chalk focus:outline-none"
        />
        <span className="tabular text-xs whitespace-nowrap text-dim">{showing} shown</span>
      </div>
    </div>
  );
}
