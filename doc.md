
# Ground Game - Documentation

This document provides a comprehensive overview of the Ground Game Fantasy Football Draft Helper application, including its architecture, functionality, and setup instructions.

## 1. Overview

Ground Game is a fantasy football draft assistant that utilizes a Value-Based Drafting (VBD) model to provide data-driven insights during fantasy drafts. The application consists of a Python backend that handles data processing and core logic, and a Next.js frontend for the user interface.

### 1.1. Core Features

*   **Value-Based Drafting (VBD):** The application's core logic is built around the VBD model, which calculates player value relative to their position.
*   **VORP (Value Over Replacement Player):** The primary metric for ranking players, indicating a player's value over a readily available replacement-level player.
*   **VONA (Value Over Next Available):** A metric that helps in making draft decisions by comparing a player's value to the best player likely to be available at your next pick.
*   **Draft Simulation:** A full draft simulation engine that supports both snake and standard draft formats, with CPU-controlled teams making intelligent picks.
*   **Live Draft Assistant:** The ability to connect to a live Sleeper draft and receive real-time advice.
*   **Web-Based UI:** A user-friendly interface for interacting with the draft room, viewing player data, and making picks.

## 2. Architecture

The application is divided into two main components: a backend API built with FastAPI and a frontend web application built with Next.js.

### 2.1. Backend

The backend is responsible for all data handling, calculations, and draft logic.

*   **API (`main.py`):** A FastAPI application that exposes endpoints for starting and managing drafts, getting draft state, and making picks.
*   **Data Services (`data_service.py`):** Handles all interactions with the PostgreSQL database, including loading player data.
*   **Draft Services (`draft_service.py`, `draft_manager_service.py`):** Manages the draft lifecycle, including draft initialization, state management, and processing picks.
*   **VBD Service (`vbd_service.py`):** Contains the core logic for calculating VORP and VONA.
*   **Simulation Service (`simulation_service.py`):** Implements the logic for CPU-controlled picks in simulated drafts.
*   **Configuration (`config.py`):** Stores default settings for the application, such as roster construction and draft parameters.

### 2.2. Frontend

The frontend provides the user interface for the draft room.

*   **Draft Room (`/draft/[session_id]/page.tsx`):** The main interface for the draft, displaying available players, the draft log, and the user's team.
*   **API Interaction:** The frontend communicates with the backend via HTTP requests to the FastAPI endpoints.
*   **State Management:** The draft state is managed within the `DraftRoom` component using React's `useState` and `useEffect` hooks.

## 3. Database Schema

The application uses a PostgreSQL database to store player data. The schema is defined in `schema.sql`.

*   **`players` table:**
    *   `sleeper_id` (Primary Key): The player's ID from Sleeper.
    *   `display_name`: The player's full name.
    *   `normalized_name`: A normalized version of the player's name for easier matching.
    *   `team`: The player's NFL team.
    *   `pos`: The player's position.
    *   `std_adp`, `half_ppr_adp`, `ppr_adp`: Average Draft Position (ADP) for different scoring formats.
    *   `std_proj_pts`, `half_ppr_proj_pts`, `ppr_proj_pts`: Projected fantasy points for different scoring formats.

## 4. Setup and Usage

### 4.1. Prerequisites

*   Python 3.8+
*   Node.js and npm
*   PostgreSQL

### 4.2. Installation

1.  **Clone the repository:**
    ```bash
    git clone <repository_url>
    cd ground-game
    ```
2.  **Backend Setup:**
    ```bash
    pip install -r requirements.txt
    ```
3.  **Frontend Setup:**
    ```bash
    cd frontend
    npm install
    ```
4.  **Database Setup:**
    *   Create a PostgreSQL database.
    *   Create a `.env` file in the `backend` directory with your database credentials (see `backend/services/data_service.py` for required variables).
    *   Run the `schema.sql` script to create the `players` table.

### 4.3. Running the Application

1.  **Start the backend server:**
    ```bash
    uvicorn backend.main:app --reload
    ```
2.  **Start the frontend development server:**
    ```bash
    cd frontend
    npm run dev
    ```
3.  Open your browser to `http://localhost:3000` to access the application.

## 5. API Endpoints

The backend exposes the following API endpoints:

*   `POST /draft/start`: Initializes a new draft session.
*   `GET /draft/{session_id}/state`: Retrieves the current state of a draft.
*   `POST /draft/{session_id}/pick`: Submits a player pick for the user.
*   `POST /draft/{session_id}/simulate-pick`: Simulates the next CPU pick.
*   `GET /draft/{session_id}/poll-live`: Polls for updates in a live draft.
*   `POST /draft/{session_id}/calculate-vona`: Calculates VONA for a list of players.
