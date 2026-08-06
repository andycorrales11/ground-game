# Ground Game - Fantasy Football Draft Helper

Ground Game is a fantasy football draft helper that leverages a Value-Based Drafting (VBD) model to provide data-driven insights during your fantasy draft. It runs as a FastAPI backend serving a Next.js web UI, and supports both draft simulation against CPU opponents and live assistance during a real Sleeper draft.

## Backend Functionality

The backend is built in Python and is responsible for data ingestion, VBD calculations, and draft simulation.

### Data Ingestion

The data ingestion process is handled by a series of scripts that download and process data from various sources:

*   **Sleeper**: Player information and IDs.
*   **nflverse**: Player stats and roster information.
*   **FantasyPros**: Average Draft Position (ADP) data.

This data is cleaned, merged, and stored in Parquet files for efficient access.

### Value-Based Drafting (VBD) Model

The core of the application is the VBD model, which calculates the value of each player relative to a "replacement-level" player at the same position. This provides a much more nuanced view of player value than standard rankings.

*   **VORP (Value Over Replacement Player)**: This is the primary metric used to rank players. It is calculated for each player based on their projected fantasy points and the fantasy points of a replacement-level player at their position.
*   **VONA (Value Over Next Available)**: This metric helps with draft decisions by calculating the value of drafting a player now versus waiting until your next pick. It does this by simulating the draft until your next turn and showing the value of the player you are considering versus the best player that will be available at your next pick.

### Draft Simulation

The application includes a full draft simulation engine that can be accessed via the CLI.

*   **Snake and Standard Drafts**: Supports both snake and standard draft formats.
*   **CPU Logic**: CPU-controlled teams make intelligent picks based on a combination of Best Player Available (BPA), positional need, and positional scarcity.
*   **Interactive Draft Room**: The web UI provides an interactive draft room where you can see the best available players, filter by position, and make your picks.

## How to Run the Application

Requires Python 3.10+ (the codebase uses PEP 604 union syntax), Node.js, and PostgreSQL.

1.  **Install dependencies**:
    ```bash
    pip install -r requirements.txt
    cd frontend && npm install
    ```
2.  **Set up the database**. Create a PostgreSQL database, apply the schema, and populate `.env`
    with `DB_HOST`, `DB_NAME`, `DB_USER`, and `DB_PASSWORD`:
    ```bash
    psql -d ground_game_db -f schema.sql
    ```
3.  **Ingest player data** (expects FantasyPros ADP and projection CSVs under `data/`):
    ```bash
    python -m backend.ingest.ingest_to_db
    ```
4.  **Start the backend** (from the repository root):
    ```bash
    uvicorn backend.main:app --reload --port 8000
    ```
5.  **Start the frontend** in a second terminal, then open http://localhost:3000:
    ```bash
    cd frontend && npm run dev
    ```