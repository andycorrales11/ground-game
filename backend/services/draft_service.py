from time import sleep
import pandas as pd
import argparse
from .draft import Draft, Team
from backend import config
import glob

def picks(pick : int, order : str = 'snake', teams : int = config.DEFAULT_TEAMS, rounds : int = config.DEFAULT_ROUNDS) -> list[int]:
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
    parser.add_argument("--teams", type=int, default=config.DEFAULT_TEAMS, help="Number of teams")
    parser.add_argument("--rounds", type=int, default=config.DEFAULT_ROUNDS, help="Number of rounds")
    parser.add_argument("--format", type=str, default=config.DEFAULT_DRAFT_FORMAT, help="Draft format (e.g., STD, PPR)")
    args = parser.parse_args()

    result = picks(args.pick, args.order, args.teams, args.rounds)
    print("Your picks:", result)
    
    path = config.PLAYER_ADP_DIR / "*_adp.parquet"
    files = sorted(glob.glob(str(path)))
    if not files:
        print(f"[error] No player ADP files found in {config.PLAYER_ADP_DIR}")
        return
    latest_file = files[-1]
    print(f"Loading players from {latest_file}...")
    all_players = pd.read_parquet(latest_file)

    draft = Draft(all_players, args.format, args.teams, args.rounds)
    team = Team()
    i = 0
    while i < args.rounds:
        print(f"\nRound {i + 1}: Pick {result[i]}")
        sleep(.5)
        print("Best available left : ")
        sleep(.5)
        adp_col = f'ADP_{args.format}'
        available_players = draft.get_available_players()
        print(available_players.sort_values(by=[adp_col]).head(10))
        sleep(1)
        pick = input("Pick player to draft (Name) : ")
        pos = draft.draft_player(pick)
        sleep(1)
        if pos is None:
            print(f"[error] Invalid name or player already drafted.")
            continue
        try:
            team.add_player(pick, pos)
        except Exception as e:
            print(f"[error] Could not add player to team: {e}")
            continue
        print(f"Drafting {pick}, {pos}")
        sleep(2)
        print("Current Roster after pick: ")
        print(team.roster)
        i += 1


if __name__ == "__main__":
    main()