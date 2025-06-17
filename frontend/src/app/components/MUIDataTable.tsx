"use client";

import * as React from 'react';
import Box from '@mui/material/Box';
import { DataGrid, GridColDef } from '@mui/x-data-grid';

interface MUIDataTableProps {
  endpoint: string;
  title?: string;
  advancedStatRows?: string[];
}

export default function MUIDataTable({ endpoint, title, advancedStatRows }: MUIDataTableProps) {
  const [rows, setRows] = React.useState<any[]>([]);
  const [columns, setColumns] = React.useState<GridColDef[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    const fetchData = async () => {
      try {
        const res = await fetch(endpoint);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        if (!Array.isArray(data)) throw new Error('Expected array response');


        const keys = Object.keys(data[0] || {});
        const cols: GridColDef[] = keys.map((key) => ({
          field: key,
          headerName: key.replace(/_/g, ' ').toUpperCase(),
          flex: 1,
          sortable: true,
        }));

        // Attach unique id for DataGrid
        const withId = data.map((row: any, index: number) => ({
          id: row.id ?? index,
          ...row,
        }));

        setColumns(cols);
        setRows(withId);
      } catch (err: any) {
        console.error(err);
        setError('Failed to load data.');
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [endpoint]);

  if (loading) return <Box p={2}>Loading...</Box>;
  if (error) return <Box p={2} color="error.main">{error}</Box>;
  if (rows.length === 0) return <Box p={2}>No data available.</Box>;

  return (
    <Box sx={{ height: 600, width: '100%' }}>
      {title && <Box component="h2" sx={{ mb: 2, fontSize: '1.25rem', fontWeight: '500' }}>{title}</Box>}
      <DataGrid
        rows={rows}
        columns={columns}
        initialState={{
          pagination: { paginationModel: { pageSize: 25 } },
        }}
        pageSizeOptions={[25, 50]}
        checkboxSelection
        disableRowSelectionOnClick
        columnVisibilityModel={
            advancedStatRows.reduce((model, col) => {
                model[col] = false;
                return model;
            }, {} as Record<string, boolean>)
        }
      />
    </Box>
  );
}
