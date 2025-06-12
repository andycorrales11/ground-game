import PlayerTable from "./components/PlayerTable";

// Define the Player type to match the PlayerTable interface
import { Player } from "./components/PlayerTable";

// Fetch player data from the FastAPI backend
async function getPlayers(): Promise<Player[]> {
  const res = await fetch("http://localhost:8000/api/players");
  if (!res.ok) throw new Error("Failed to fetch players");
  const data = await res.json();
  // Map API response to PlayerTable's Player interface
  return data.map((p: any, idx: number) => ({
    id: p.sleeper_id ? Number(p.sleeper_id) : idx,
    name: p.full_name || `${p.first_name || ''} ${p.last_name || ''}`.trim(),
    team: p.team || '',
    position: p.position || '',
  })).filter((player: Player) => !isNaN(player.id));
}

export default async function Home() {
  const players = await getPlayers();
  return (
    <>
      <PlayerTable players={players}/>
    </>
  );
}
