import MUIDataTable from '@/app/components/MUIDataTable';
import Header from '@/app/components/Header';

export default function HomePage() {
  return (
    <main className="p-8">
      <Header />
      <MUIDataTable 
        endpoint="/api/players/rbs?limit=100" 
        title="2024 RB Stats" 
        advancedStatRows={['player_id','rushing_fumbles_lost',
       'rushing_first_downs', 'rushing_epa', 'rushing_2pt_conversions', 
       'fantasy_points', 'fantasy_points_ppr']}
      />
    </main>
  );
}
