import MUIDataTable from '@/app/components/MUIDataTable';
import Header from '@/app/components/Header';
import { useSearchParams } from 'react-router-dom';


export default function HomePage() {
  return (
    <main className="p-8">
      <Header />
      <MUIDataTable
        endpoint="/api/players/qbs/"
        title="2024 QB Stats"
        advancedStatRows={['player_id','sack_yards',
       'sack_fumbles', 'sack_fumbles_lost', 'passing_air_yards',
       'passing_yards_after_catch', 'passing_first_downs', 'passing_epa',
       'passing_2pt_conversions', 'pacr', 'fantasy_points', 'fantasy_points_ppr']}
      />
    </main>
  );
}
