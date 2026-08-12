interface Props {
  tier: number;
  pos: string;
  /** Points given up by waiting past this tier. */
  drop: number;
  colSpan: number;
}

/*
  The signature.

  Everywhere else this app reports value as a number in a column. Here it is a
  line drawn across the board at the place where waiting starts costing you --
  the one thing a value-based draft model knows that a printed cheat sheet does
  not. It is chalk, not colour, for the same reason the rail is: a cliff is not
  a position.
*/
export default function CliffRule({ tier, pos, drop, colSpan }: Props) {
  return (
    <tr>
      <td colSpan={colSpan} className="p-0">
        <div className="flex items-center gap-3 py-2.5" role="separator">
          <span className="h-px flex-1 bg-chalk/30" />
          <span className="font-display text-[11px] font-semibold uppercase tracking-[0.16em] whitespace-nowrap text-chalk/80">
            Tier {tier} ends
            <span className="ml-2 font-normal text-dim">
              next {pos} is <span className="tabular">{drop.toFixed(1)}</span> worse
            </span>
          </span>
          <span className="h-px flex-1 bg-chalk/30" />
        </div>
      </td>
    </tr>
  );
}
