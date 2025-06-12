import Header from "@/app/components/Header";
import PlayerTable from "@/app/components/PlayerTable";

import { Player } from "@/app/components/PlayerTable";


async function getPlayers(): Promise<Player[]> {
  const res = await fetch("http://localhost:8000/api/players?limit=100");
  if (!res.ok) throw new Error("Failed to fetch players");
  const data = await res.json();

  return data.map((p: any, idx: number) => ({
    id: p.sleeper_id ? Number(p.sleeper_id) : idx,
    name: p.full_name || `${p.first_name || ''} ${p.last_name || ''}`.trim(),
    team: p.team || '',
    position: p.position || '',
  }));
}

export default async function Home() {
  const players = await getPlayers();
  return (
    <>
      <Header />
      <PlayerTable players={players}/>
    </>
  );
}
