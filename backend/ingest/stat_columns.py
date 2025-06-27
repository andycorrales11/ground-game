seasonal_columns = ['player_id', 'season', 'season_type', 'completions', 'attempts',
    'passing_yards', 'passing_tds', 'interceptions', 'sacks', 'sack_yards',
    'sack_fumbles', 'sack_fumbles_lost', 'passing_air_yards',
    'passing_yards_after_catch', 'passing_first_downs', 'passing_epa',
    'passing_2pt_conversions', 'pacr', 'carries', 'rushing_yards',
    'rushing_tds', 'rushing_fumbles', 'rushing_fumbles_lost',
    'rushing_first_downs', 'rushing_epa', 'rushing_2pt_conversions',
    'receptions', 'targets', 'receiving_yards', 'receiving_tds',
    'receiving_fumbles', 'receiving_fumbles_lost', 'receiving_air_yards',
    'receiving_yards_after_catch', 'receiving_first_downs', 'receiving_epa',
    'receiving_2pt_conversions', 'racr', 'target_share', 'air_yards_share',
    'wopr_x', 'special_teams_tds', 'fantasy_points', 'fantasy_points_ppr',
    'games', 'tgt_sh', 'ay_sh', 'yac_sh', 'wopr_y', 'ry_sh', 'rtd_sh',
    'rfd_sh', 'rtdfd_sh', 'dom', 'w8dom', 'yptmpa', 'ppr_sh']

player_columns = ['first_name', 'last_name', 'position', 'gsis_id',
    'display_name', 'current_team_id','jersey_number',
    'position_group', 'short_name', 'smart_id', 'status',
    'status_description_abbr', 'status_short_description', 'team_abbr',
    'uniform_number', 'height', 'weight', 'college_name',
    'years_of_experience', 'birth_date', 'team_seq', 'suffix']

qb_columns = ['player_id', 'season', 'season_type', 'completions', 'attempts',
    'passing_yards', 'passing_tds', 'interceptions', 'sacks', 'sack_yards',
    'sack_fumbles', 'sack_fumbles_lost', 'passing_air_yards',
    'passing_yards_after_catch', 'passing_first_downs', 'passing_epa',
    'passing_2pt_conversions', 'pacr', 'fantasy_points', 'fantasy_points_ppr']

rb_columns = ['player_id', 'season', 'season_type', 'carries', 'rushing_yards',
    'rushing_tds', 'rushing_fumbles', 'rushing_fumbles_lost',
    'rushing_first_downs', 'rushing_epa', 'rushing_2pt_conversions', 
    'fantasy_points', 'fantasy_points_ppr']

wr_columns = ['player_id', 'season', 'season_type', 'receptions', 'targets', 'receiving_yards', 'receiving_tds',
    'receiving_fumbles', 'receiving_fumbles_lost', 'receiving_air_yards',
    'receiving_yards_after_catch', 'receiving_first_downs', 'receiving_epa',
    'receiving_2pt_conversions', 'racr', 'target_share', 'air_yards_share',
    'wopr_x', 'special_teams_tds', 'fantasy_points', 'fantasy_points_ppr',
    'games', 'tgt_sh', 'ay_sh', 'yac_sh', 'wopr_y', 'ry_sh', 'rtd_sh',
    'rfd_sh', 'rtdfd_sh', 'dom', 'w8dom', 'yptmpa', 'ppr_sh']

sleeper_columns = ['sleeper_id', 'injury_notes', 'swish_id', 'first_name', 'age', 
    'injury_body_part', 'metadata', 'active', 'last_name', 'injury_start_date',
    'stats_id', 'college', 'search_rank', 'number', 'player_id', 'fantasy_data_id',
    'birth_city', 'status', 'high_school', 'birth_state', 'height',
    'search_full_name', 'fantasy_positions', 'team_changed_at', 'competitions',
    'rotowire_id', 'full_name', 'weight', 'rotoworld_id', 'gsis_id', 'news_updated',
    'team', 'depth_chart_position', 'practice_description', 'birth_country',
    'search_first_name', 'hashtag', 'practice_participation', 'yahoo_id', 
    'pandascore_id', 'injury_status', 'oddsjam_id', 'opta_id', 'position', 
    'search_last_name', 'sport', 'espn_id', 'birth_date', 'sportradar_id', 
    'years_exp', 'depth_chart_order', 'team_abbr', 'display_name']