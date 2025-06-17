"use client";
import { useEffect, useState } from 'react';

interface GenericDataTableProps {
  endpoint: string;
  title?: string;
}

export default function GenericDataTable({ endpoint, title }: GenericDataTableProps) {
  const [data, setData] = useState<Record<string, any>[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const res = await fetch(endpoint);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const json = await res.json();
        if (Array.isArray(json)) setData(json);
        else throw new Error('Expected array response');
      } catch (err: any) {
        console.error(err);
        setError('Failed to load data.');
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [endpoint]);

  if (loading) return <p className="p-4">Loading...</p>;
  if (error) return <p className="p-4 text-red-500">{error}</p>;
  if (data.length === 0) return <p className="p-4">No data available.</p>;

  const columns = Object.keys(data[0]);

  return (
    <div className="overflow-x-auto p-4 max-w-screen w-full">
      {title && <h2 className="text-xl font-semibold mb-4">{title}</h2>}
      <table className="min-w-full table-auto border-collapse border border-gray-200">
        <thead>
          <tr className="bg-gray-100 text-black">
            {columns.map((col) => (
              <th key={col} className="border px-4 py-2 text-left text-transform: uppercase">
                {col.replace(/_/g, ' ')}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.map((row, idx) => (
            <tr key={idx} className="hover:bg-gray-600">
              {columns.map((col) => (
                <td key={col} className="border px-4 py-2 text-sm">
                  {row[col] != null ? String(row[col]) : '-'}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
