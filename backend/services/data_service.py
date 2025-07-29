"""
Service for loading data from the database.
"""
import logging
import os
import pandas as pd
import psycopg
from dotenv import load_dotenv

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
        logging.error(f"Error connecting to the database: {e}")
        return None

def load_player_data() -> pd.DataFrame | None:
    """Loads all player data from the database."""
    try:
        conn = get_db_connection()
        if conn is None:
            logging.error("Failed to get database connection.")
            return None
        
        query = "SELECT * FROM players"
        df = pd.read_sql(query, conn)
        conn.close()
        
        logging.info(f"Successfully loaded {len(df)} players from the database.")
        return df
        
    except Exception as e:
        logging.error(f"An error occurred while loading data from the database: {e}")
        return None




