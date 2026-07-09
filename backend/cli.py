import argparse
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s - %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

def cmd_import_liked(args):
    from backend.auth.spotify_auth import get_spotify_client
    from backend.importers.liked_songs import import_liked_songs
    client = get_spotify_client()
    incremental = not args.full
    print(f"\n{'Full' if args.full else 'Incremental'} liked songs import starting...\n")
    counts = import_liked_songs(client, incremental=incremental)
    print(f"\nDone: {counts['found']} found | {counts['new']} new | {counts['errors']} errors\n")

def cmd_import_features(args):
    from backend.auth.spotify_auth import get_spotify_client
    from backend.importers.audio_features import import_audio_features
    client = get_spotify_client()
    print("\nFetching audio features...\n")
    counts = import_audio_features(client)
    print(f"\nDone: {counts['success']} fetched | {counts['unavailable']} unavailable | {counts['errors']} errors\n")

def cmd_import_artists(args):
    from backend.auth.spotify_auth import get_spotify_client
    from backend.importers.artists import import_artist_genres
    client = get_spotify_client()
    print("\nFetching artist genres...\n")
    counts = import_artist_genres(client)
    print(f"\nDone: {counts['updated']} artists updated | {counts['errors']} errors\n")

def cmd_import_history(args):
    from backend.importers.streaming_history_importer import import_streaming_history
    print(f"\nImporting streaming history from: {args.export}\n")
    counts = import_streaming_history(args.export)
    print(
        f"\nDone: {counts['new']} new plays | {counts['duplicates']} duplicates | "
        f"{counts['stubbed']} new tracks discovered (streamed but never liked)\n"
    )

def cmd_enrich_tracks(args):
    from backend.auth.spotify_auth import get_spotify_client
    from backend.importers.track_enrichment import enrich_stub_tracks
    client = get_spotify_client()
    print("\nEnriching stub tracks (streamed but never liked) with full Spotify metadata...\n")
    counts = enrich_stub_tracks(client)
    print(f"\nDone: {counts['enriched']} enriched | {counts['errors']} errors | {counts['processed']} processed\n")

def cmd_stats(args):
    from backend.db.database import init_db, db_conn
    import json
    from collections import Counter
    init_db()
    with db_conn() as conn:
        liked    = conn.execute("SELECT COUNT(*) as n FROM liked_songs").fetchone()["n"]
        tracks   = conn.execute("SELECT COUNT(*) as n FROM tracks").fetchone()["n"]
        artists  = conn.execute("SELECT COUNT(*) as n FROM artists").fetchone()["n"]
        albums   = conn.execute("SELECT COUNT(*) as n FROM albums").fetchone()["n"]
        features = conn.execute("SELECT COUNT(*) as n FROM audio_features").fetchone()["n"]
        with_genres = conn.execute("SELECT COUNT(*) as n FROM artists WHERE genres IS NOT NULL AND genres != '[]'").fetchone()["n"]
        by_status = conn.execute("SELECT review_status, COUNT(*) as n FROM liked_songs GROUP BY review_status").fetchall()

        # Top genres
        rows = conn.execute("""
            SELECT a.genres FROM artists a
            JOIN tracks t ON t.primary_artist_id = a.id
            JOIN liked_songs ls ON ls.track_id = t.id
            WHERE a.genres IS NOT NULL AND a.genres != '[]'
        """).fetchall()
        genre_counts = Counter()
        for r in rows:
            try:
                for g in json.loads(r["genres"]):
                    genre_counts[g] += 1
            except: pass

    print("\n--- Music Intelligence - Local DB Stats ---")
    print(f"  Liked songs   : {liked:,}")
    print(f"  Tracks        : {tracks:,}")
    print(f"  Artists       : {artists:,} ({with_genres:,} with genres)")
    print(f"  Albums        : {albums:,}")
    print(f"  Audio features: {features:,} / {tracks:,}")
    print("\n  Review status:")
    for row in by_status:
        print(f"    {row['review_status']:20s}: {row['n']:,}")
    if genre_counts:
        print("\n  Top genres:")
        for genre, count in genre_counts.most_common(8):
            print(f"    {genre:25s}: {count:,}")
    print("-------------------------------------------\n")

def cmd_serve(args):
    from backend.api.server import run
    run()

def main():
    parser = argparse.ArgumentParser(description="Music Intelligence CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_liked = sub.add_parser("import-liked")
    p_liked.add_argument("--full", action="store_true")
    p_liked.set_defaults(func=cmd_import_liked)

    p_feat = sub.add_parser("import-features")
    p_feat.set_defaults(func=cmd_import_features)

    p_artists = sub.add_parser("import-artists", help="Fetch genre data for all artists")
    p_artists.set_defaults(func=cmd_import_artists)

    p_history = sub.add_parser("import-history", help="Import Spotify Extended Streaming History export")
    p_history.add_argument("--export", required=True, help="Path to 'Spotify Extended Streaming History' folder")
    p_history.set_defaults(func=cmd_import_history)

    p_enrich = sub.add_parser("enrich-tracks", help="Backfill full metadata for tracks discovered via streaming history")
    p_enrich.set_defaults(func=cmd_enrich_tracks)

    p_stats = sub.add_parser("stats")
    p_stats.set_defaults(func=cmd_stats)

    p_serve = sub.add_parser("serve")
    p_serve.set_defaults(func=cmd_serve)

    args = parser.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()
