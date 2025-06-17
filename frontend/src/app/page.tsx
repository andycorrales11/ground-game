'use client';
import Header from "./components/Header";
import Grid from '@mui/material/Grid';
import * as React from 'react';

export default function Home() {
  return (
    <>
      <Header />
      <Grid container spacing={2} sx={{ justifyContent: 'center', padding: 2}}>
        <Grid size={{xs: 6, md: 8}} sx = {{ textAlign: 'center' }}>
            <h1>Welcome to Ground Game</h1>
            <p>This dashboard provides advanced statistics for players across various positions, including WRs, QBs, and RBs.</p>
            <p>Use the navigation to explore player stats and make informed decisions for your fantasy football team.</p>
        </Grid>
      </Grid>
    </>
  );
}
