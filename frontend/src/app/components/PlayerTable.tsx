import React from 'react';

export interface Player {
  id: number;
  name: string;
  team: string;
  position: string;
}

interface PlayerTableProps {
  players: Player[];
}

const PlayerTable: React.FC<PlayerTableProps> = ({ players }) => {
  return (
    <div className="overflow-x-auto border-2 border-black rounded-lg">
      <table className="min-w-full divide-y divide-gray-200">
        <thead className="bg-yellow-100">
          <tr>
            <th scope="col" className="px-6 py-3 text-left text-s text-cyan-800 font-medium uppercase tracking-wider">
              ID
            </th>
            <th scope="col" className="px-6 py-3 text-left text-s text-cyan-800 font-medium uppercase tracking-wider">
              Name
            </th>
            <th scope="col" className="px-6 py-3 text-left text-s text-cyan-800 font-medium uppercase tracking-wider">
              Team
            </th>
            <th scope="col" className="px-6 py-3 text-left text-s text-cyan-800 font-medium uppercase tracking-wider">
              Position
            </th>
          </tr>
        </thead>
        <tbody className="bg-yellow-50 divide-y divide-gray-200">
          {players.map((player) => (
            <tr key={player.id}>
              <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                {player.id}
              </td>
              <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                {player.name}
              </td>
              <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                {player.team}
              </td>
              <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                {player.position}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default PlayerTable;
