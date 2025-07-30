from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List

from backend.services.draft_manager_service import DraftManagerService

from pydantic import BaseModel
from backend.services.draft_manager_service import DraftManagerService

class DraftSettings(BaseModel):
    pick_slot: int
    draft_id: str | None = None # For live mode
    non_interactive: bool = False # For simulation auto-pick
    teams: int | None = None # For simulation
    rounds: int | None = None # For simulation
    format: str | None = None # For simulation
    order: str | None = None # For simulation

class PlayerPick(BaseModel):
    player_name: str

class VonaCalculationRequest(BaseModel):
    player_names: List[str]

app = FastAPI()

# Configure CORS to allow your Next.js frontend to access the backend
# In a production environment, you should restrict origins to your frontend's domain.
origins = [
    "http://localhost",
    "http://localhost:3000", # Default Next.js development server port
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/draft/start")
async def start_draft(settings: DraftSettings):
    result = DraftManagerService.initialize_draft(
        pick_slot=settings.pick_slot,
        draft_id=settings.draft_id,
        non_interactive=settings.non_interactive,
        teams=settings.teams,
        rounds=settings.rounds,
        format=settings.format,
        order=settings.order
    )
    if "error" in result:
        return JSONResponse(content=result, status_code=400)
    return result

@app.get("/draft/{session_id}/state")
async def get_draft_state(session_id: str, position_filter: str | None = None, sort_by: str | None = None):
    result = DraftManagerService.get_current_draft_state(session_id, position_filter, sort_by)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result

@app.post("/draft/{session_id}/pick")
async def make_pick(session_id: str, player_pick: PlayerPick):
    result = DraftManagerService.process_user_pick(session_id, player_pick.player_name)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result

@app.post("/draft/{session_id}/simulate-pick")
async def simulate_next_pick(session_id: str):
    result = DraftManagerService.process_cpu_pick(session_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result

@app.get("/draft/{session_id}/poll-live")
async def poll_live_draft(session_id: str):
    result = DraftManagerService.poll_live_draft_updates(session_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result

@app.post("/draft/{session_id}/calculate-vona")
async def calculate_vona_endpoint(session_id: str, request: VonaCalculationRequest):
    result = DraftManagerService.calculate_vona_for_display(session_id, request.player_names)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result
