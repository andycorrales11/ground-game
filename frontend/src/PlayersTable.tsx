import { useEffect, useState } from 'react';
import { type ColumnDef, flexRender, getCoreRowModel, useReactTable } from '@tanstack/react-table';
import axios from 'axios';

interface Player {
  sleeper_id: string;
  full_name: string;
  position: string;
  team: string;
  // add other fields you care about
}

export function PlayersTable() {
  const [data, setData] = useState<Player[]>([]);

  useEffect(() => {
    axios.get<Player[]>('/api/players?limit=500')
         .then(r => setData(r.data));
  }, []);

  const columns: ColumnDef<Player>[] = [
    { accessorKey: 'sleeper_id', header: 'ID' },
    { accessorKey: 'full_name',  header: 'Name' },
    { accessorKey: 'position',   header: 'Pos' },
    { accessorKey: 'team',       header: 'Team' },
  ];

  const table = useReactTable({ data, columns, getCoreRowModel: getCoreRowModel() });

  return (
    <table className="min-w-full border">
      <thead>{table.getHeaderGroups().map(hg => (
        <tr key={hg.id}>
          {hg.headers.map(h => (
            <th key={h.id} className="border px-2 py-1">
              {flexRender(h.column.columnDef.header, h.getContext())}
            </th>
          ))}
        </tr>
      ))}</thead>
      <tbody>{table.getRowModel().rows.map(row => (
        <tr key={row.id}>
          {row.getVisibleCells().map(cell => (
            <td key={cell.id} className="border px-2 py-1">
              {flexRender(cell.column.columnDef.cell, cell.getContext())}
            </td>
          ))}
        </tr>
      ))}</tbody>
    </table>
  );
}
