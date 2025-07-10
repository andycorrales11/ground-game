from ingest import ingest_adp, ingest_players, ingest_stats

def main():
    ingest_players.main()
    ingest_adp.main()
    ingest_stats.main()