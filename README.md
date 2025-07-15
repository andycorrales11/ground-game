# Ground Game - Fantasy Football Draft Helper

Ground Game is a fantasy football draft helper that leverages a Value-Based Drafting (VBD) model to provide data-driven insights during your fantasy draft. The application is currently in the backend development phase, with a command-line interface (CLI) to access the core logic.

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
*   **Interactive Draft Room**: The CLI provides an interactive draft room where you can see the best available players, filter by position, and make your picks.

## How to Run the Application

1.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```
2.  **Run the Draft**:
    ```bash
    python api.py <your_pick_number> --teams <num_teams> --format <PPR|HalfPPR|STD>
    ```
    For example, to start a 12-team PPR draft where you have the 3rd pick, you would run:
    ```bash
    python api.py 3 --teams 12 --format PPR
    ```