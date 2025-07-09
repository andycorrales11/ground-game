from time import sleep
import pandas as pd
import argparse
from .draft import Draft, Team

def picks(pick : int, order : str = 'snake', teams : int = 12, rounds : int = 12) -> list[int]:
    picks = []

    match order:
        case 'snake':
            for i in range(rounds):
                if i % 2 == 0:
                    picks.append((i * teams) + pick)
                else:
                    picks.append((i * teams) + (teams - pick + 1))
        case 'normal':
            for i in range(rounds):
                picks.append((i * teams) + pick)

    return picks

def main():
    parser = argparse.ArgumentParser(description="Draft pick order calculator")
    parser.add_argument("pick", type=int, help="Your pick number (1-based)")
    parser.add_argument("--order", choices=["snake", "normal"], default="snake", help="Draft order type")
    parser.add_argument("--teams", type=int, default=12, help="Number of teams")
    parser.add_argument("--rounds", type=int, default=20, help="Number of rounds")
    args = parser.parse_args()

    result = picks(args.pick, args.order, args.teams, args.rounds)
    print("Your picks:", result)
    all_players = pd.read_parquet("data/players_adp/2025-07-09_adp.parquet")
    draft = Draft(all_players, 'STD', args.teams, args.rounds)
    team = Team()
    for i in range(args.rounds):
        print(f"Round {i + 1}:")
        sleep(.5)
        print("Best available left : ")
        sleep(.5)
        print(draft.players.sort_values(by=['ADP']).head(10))
        sleep(1)
        pick = input("Pick player to draft (Name) : ")
        pos = draft.draft_player(pick)
        print(f"Drafting {pick}, {pos}")
        sleep(1)
        team.add_player(pick, pos)
        print("Current Roster after pick: ")
        print(team.roster)


if __name__ == "__main__":
    main()