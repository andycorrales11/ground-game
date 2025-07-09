import pandas as pd
from typing import List, Dict

default_roster = ["QB1","RB1","RB2","WR1","WR2","TE1","FLEX1","FLEX2","K","DEF","BN1","BN2","BN3","BN4","BN5","BN6","BN6","BN6","BN7","BN8"]

# test = pd.DataFrame({'display_name' : ['Tom Brady', 'Patrick Mahomes', 'Tua Tagovailoa']})

class Draft:
    def __init__(self, players : pd.DataFrame, format : str = 'STD', teams : int = 12, rounds : int = 20, roster : List[str] = default_roster):
        self.players = players
        self.format = format
        self.teams = teams
        self.rounds = rounds
        self.roster = roster

    def draft_player(self, player : str) -> str:
        mask = self.players['display_name'] == player
        player_row = self.players[mask]
        if not player_row.empty:
            position = player_row.iloc[0]['position']
            self.players = self.players[~mask]
            return position
        return None

class Team:
    def __init__(self, roster : List[str] = default_roster):
        self.roster = Dict.fromkeys(roster)
    
    def add_player(self, player : str, pos : str):
        for slot in self.roster:
            if slot.startswith(pos) and self.roster.get(slot) is None:
                self.roster[slot] = player
                break
            elif pos == ('WR' or 'RB' or 'TE') and slot.startswith('FLEX') and self.roster.get(slot) is None:
                self.roster[slot] = player
                break
            elif slot.startswith('BN'):
                self.roster[slot] = player
                break



# draft = Draft(test)
# print(draft.players)
# draft.draft_player('Tom Brady')
# print(draft.players)

# team = Team()
# team.add_player('Tyreek Hill', 'WR')
# team.add_player('Tua Tagovailoa', 'QB')
# team.add_player('Jaylen Waddle', 'WR')
# team.add_player('Quinn Ewers', 'QB')
# team.add_player('Malik Nabers', 'WR')

# print(team.roster)