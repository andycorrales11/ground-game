def picks(pick : int, order : str = 'snake', teams : int = 12, rounds : int = 12) -> list[int]:
    picks = []
    match order:
        case 'snake':
            for i in range(rounds):
                if i % 2 == 0:
                    picks.append((i * teams) + pick)
                else:
                    picks.append((i * teams) + (teams - pick + 1))
    print(picks)
    return picks

