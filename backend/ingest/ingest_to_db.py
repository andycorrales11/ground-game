import os
import pandas as pd
import psycopg
from dotenv import load_dotenv
import nfl_data_py as nfl
import re

# Load environment variables from .env file
load_dotenv()

# --- DATABASE CONNECTION ---
DB_HOST = os.getenv("DB_HOST")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")

def get_db_connection():
    """Establishes a connection to the PostgreSQL database."""
    try:
        conn = psycopg.connect(
            host=DB_HOST,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD
        )
        return conn
    except psycopg.OperationalError as e:
        print(f"Error connecting to the database: {e}")
        return None

def normalize_name(player_name):
    """Normalizes player name by lowercasing and removing special characters."""
    if not isinstance(player_name, str):
        return None
    # Remove 'Sr.', 'Jr.', 'III', etc.
    name = re.sub(r'\s+(Sr\.|Jr\.|III|II|IV)$', '', player_name)
    # Remove apostrophes and periods, and replace spaces with underscores
    return re.sub(r"['.]", '', name).lower().replace(' ', '_')


def get_sleeper_ids():
    """Gets Sleeper IDs for a list of player names using nfl_data_py."""
    player_ids_df = nfl.import_ids()
    return player_ids_df

def prepare_data():
    """Reads and prepares player data from CSV files."""
    # --- Load ADP Data ---
    adp_path = "data/fantasy_pros_adp"
    adp_std = pd.read_csv(f"{adp_path}/FantasyPros_2025_STD_ADP.csv")
    adp_half_ppr = pd.read_csv(f"{adp_path}/FantasyPros_2025_HalfPPR_ADP.csv")
    adp_ppr = pd.read_csv(f"{adp_path}/FantasyPros_2025_PPR_ADP.csv")

    # Rename ADP columns
    adp_std.rename(columns={"AVG": "std_adp"}, inplace=True)
    adp_half_ppr.rename(columns={"AVG": "half_ppr_adp"}, inplace=True)
    adp_ppr.rename(columns={"AVG": "ppr_adp"}, inplace=True)

    # Merge ADP data
    adp_data = pd.merge(adp_std[['Player', 'POS', 'Team', 'std_adp']],
                        adp_half_ppr[['Player', 'half_ppr_adp']],
                        on='Player', how='outer')
    adp_data = pd.merge(adp_data, adp_ppr[['Player', 'ppr_adp']],
                        on='Player', how='outer')

    # --- Load Projections Data ---
    proj_path = "data/projections"
    
    # Dictionary to hold dataframes for each format
    projections_by_format = {'std': [], 'ppr': [], 'half_ppr': []}

    projection_files = [f for f in os.listdir(proj_path) if f.endswith('.csv')]

    for file_name in projection_files:
        file_path = os.path.join(proj_path, file_name)
        try:
            # Extract format from filename
            format_search = re.search(r'_(std|ppr|halfppr)\.csv$', file_name, re.IGNORECASE)
            if not format_search:
                print(f"Warning: Could not determine format for file: {file_name}")
                continue

            f = format_search.group(1).lower().replace('halfppr', 'half_ppr')
            
            df = pd.read_csv(file_path, sep='\t')
            # All projection files have Player, TM, BYE, FPS. We only need Player and FPS.
            df = df[['Player', 'FPS']]
            df.rename(columns={"Player": "display_name"}, inplace=True)
            projections_by_format[f].append(df)

        except Exception as e:
            print(f"Error processing file {file_name}: {e}")
            continue

    # Concatenate dataframes for each format and rename FPS column
    projections_data = None
    for format_key, dfs in projections_by_format.items():
        if not dfs:
            continue
        
        # Concatenate all dataframes for a given format (e.g., all std projection files)
        format_df = pd.concat(dfs, ignore_index=True)
        
        # Group by display_name to remove duplicates, taking the first non-null projection
        proj_col_name = f"{format_key}_proj_pts"
        format_df.rename(columns={"FPS": proj_col_name}, inplace=True)
        format_df = format_df.groupby('display_name').first().reset_index()
        
        # Merge with the main projections dataframe
        if projections_data is None:
            projections_data = format_df
        else:
            projections_data = pd.merge(projections_data, format_df, on='display_name', how='outer')

    # --- Merge ADP and Projections ---
    # Use display_name from projections as the primary name
    merged_data = pd.merge(adp_data, projections_data, left_on='Player', right_on='display_name', how='outer')
    merged_data['display_name'].fillna(merged_data['Player'], inplace=True)
    merged_data.drop(columns=['Player'], inplace=True)


    # --- Data Cleaning and Processing ---
    merged_data['normalized_name'] = merged_data['display_name'].apply(normalize_name)
    merged_data['pos'] = merged_data['POS'].str.replace(r'\d+', '', regex=True)

    # Get Sleeper IDs
    player_names = merged_data['display_name'].dropna().unique().tolist()
    
    # nfl_data_py has issues with some names, so we do some manual mapping
    name_map = {
        "Deebo Samuel Sr.": "Deebo Samuel",
        "Brian Robinson Jr.": "Brian Robinson",
        "Anthony Richardson Sr.": "Anthony Richardson",
        "Aaron Jones Sr.": "Aaron Jones"
    }
    player_names_for_id = [name_map.get(name, name) for name in player_names]

    player_ids = get_sleeper_ids()
    
    # Create a mapping from display name to sleeper id
    id_map = dict(zip(player_ids['name'], player_ids['sleeper_id']))

    merged_data['sleeper_id'] = merged_data['display_name'].apply(lambda x: id_map.get(name_map.get(x, x)))

    # Drop duplicates based on sleeper_id, keeping the first occurrence.
    merged_data.drop_duplicates(subset=['sleeper_id'], keep='first', inplace=True)

    # Final column selection
    final_data = merged_data[[
        'sleeper_id', 'display_name', 'normalized_name', 'Team', 'pos',
        'std_adp', 'half_ppr_adp', 'ppr_adp',
        'std_proj_pts', 'half_ppr_proj_pts', 'ppr_proj_pts'
    ]].copy()
    
    final_data.rename(columns={'Team': 'team'}, inplace=True)

    # Drop rows where sleeper_id is missing, as it's the primary key
    final_data.dropna(subset=['sleeper_id'], inplace=True)

    return final_data

def ingest_data(data):
    """Ingests the prepared data into the PostgreSQL database."""
    conn = get_db_connection()
    if not conn:
        return

    with conn.cursor() as cur:
        # Clear existing data
        cur.execute("TRUNCATE TABLE players RESTART IDENTITY;")
        print("Players table truncated.")

        # Prepare data for insertion
        data_to_insert = [tuple(row) for row in data.itertuples(index=False)]

        # Use executemany for bulk insertion
        try:
            with cur.copy("COPY players (sleeper_id, display_name, normalized_name, team, pos, std_adp, half_ppr_adp, ppr_adp, std_proj_pts, half_ppr_proj_pts, ppr_proj_pts) FROM STDIN") as copy:
                for record in data_to_insert:
                    copy.write_row(record)
            conn.commit()
            print(f"{len(data_to_insert)} records inserted successfully.")
        except Exception as e:
            print(f"Error during bulk insert: {e}")
            conn.rollback()

    conn.close()


if __name__ == "__main__":
    print("Starting data preparation...")
    prepared_data = prepare_data()
    print("Data preparation complete.")
    print("Starting data ingestion...")
    ingest_data(prepared_data)
    print("Data ingestion complete.")
