import MUIDataTable from '@/app/components/MUIDataTable';
import Header from '@/app/components/Header';

export default function HomePage() {
  return (
    <main className="p-8">
      <Header />
      <MUIDataTable 
        endpoint="/api/players/wrs?limit=40" 
        title="2024 WR Stats" 
        advancedStatRows={['player_id','receiving_fumbles', 'receiving_fumbles_lost', 'receiving_air_yards',
       'receiving_yards_after_catch', 'receiving_first_downs', 'receiving_epa',
       'receiving_2pt_conversions', 'racr', 'target_share', 'air_yards_share',
       'wopr_x', 'special_teams_tds', 'fantasy_points', 'fantasy_points_ppr',
       'games', 'tgt_sh', 'ay_sh', 'yac_sh', 'wopr_y', 'ry_sh', 'rtd_sh',
       'rfd_sh', 'rtdfd_sh', 'dom', 'w8dom', 'yptmpa', 'ppr_sh']}
      />
    </main>
  );
}
