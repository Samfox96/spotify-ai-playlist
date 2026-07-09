"""
Streaming History Importer — Phase 2 of Music Intelligence

Reads all Streaming_History_Audio_*.json files from a Spotify Extended
Streaming History export folder, filters out podcasts/audiobooks, dedupes,
and loads events into `listening_history`. Then rebuilds the derived
`track_listening_stats` aggregate table.

Usage (standalone):
    python streaming_history_importer.py --db path/to/music_intelligence.db \
        --export "C:\\path\\to\\Spotify Extended Streaming History"

To wire into your existing CLI (backend/cli.py), add a subcommand that
calls `import_streaming_history(db_path, export_dir)` — see the
`if __name__ == "__main__"` block for the exact call.

Assumptions / things to check against your actual schema:
  - Run migrations/002_listening_history.sql against your DB once before
    running this importer (or run `ensure_schema()` below, which applies it
    automatically if the tables don't exist yet).
  - track_listening_stats.spotify_uri is meant to join to your `tracks`
    table. If your tracks table's Spotify URI column isn't named
    `spotify_uri`, nothing here breaks — just update the join in whatever
    query/view you use to combine the two tables. This importer never
    writes to `tracks`, only to the two new tables.
  - A "real" play (play_count) is defined as ms_played > 30000 (30s),
    which is Spotify's own rough threshold for counting a stream. Adjust
    REAL_PLAY_THRESHOLD_MS below if you want a different cutoff.
"""

import argparse
import glob
import json
import os
import sqlite3
from datetime import datetime

REAL_PLAY_THRESHOLD_MS = 30_000

MIGRATION_SQL_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "migrations", "002_listening_history.sql"
)


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Apply the listening_history migration if tables don't already exist."""
    cur = conn.cursor()
    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='listening_history'"
    )
    if cur.fetchone() is None:
        if not os.path.exists(MIGRATION_SQL_PATH):
            raise FileNotFoundError(
                f"Migration file not found at {MIGRATION_SQL_PATH}. "
                "Place migrations/002_listening_history.sql alongside this script, "
                "or run it manually against your DB first."
            )
        with open(MIGRATION_SQL_PATH, "r", encoding="utf-8") as f:
            conn.executescript(f.read())
        conn.commit()
        print("Applied migration: listening_history + track_listening_stats tables created.")


def load_export_files(export_dir: str) -> list[dict]:
    """Load and concatenate all Streaming_History_Audio_*.json files in the export dir."""
    pattern = os.path.join(export_dir, "Streaming_History_Audio_*.json")
    files = sorted(glob.glob(pattern))
    if not files:
        raise FileNotFoundError(
            f"No Streaming_History_Audio_*.json files found in {export_dir}. "
            "Double check the path points at the 'Spotify Extended Streaming History' folder."
        )

    all_records = []
    for path in files:
        with open(path, "r", encoding="utf-8") as f:
            records = json.load(f)
        all_records.extend(records)
        print(f"  loaded {os.path.basename(path)}: {len(records)} records")
    return all_records


def import_streaming_history(db_path: str, export_dir: str) -> None:
    conn = sqlite3.connect(db_path)
    ensure_schema(conn)

    print(f"Reading export from: {export_dir}")
    records = load_export_files(export_dir)
    print(f"Total raw records loaded: {len(records)}")

    music_records = [r for r in records if r.get("spotify_track_uri")]
    skipped_non_music = len(records) - len(music_records)
    print(f"Music (track) records: {len(music_records)}  "
          f"(dropped {skipped_non_music} podcast/audiobook/empty records)")

    cur = conn.cursor()
    inserted = 0
    duplicates = 0

    for r in music_records:
        try:
            cur.execute(
                """
                INSERT INTO listening_history (
                    played_at, spotify_uri, ms_played, platform, conn_country,
                    reason_start, reason_end, shuffle, skipped, offline,
                    incognito_mode, track_name, artist_name, album_name
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    r["ts"],
                    r["spotify_track_uri"],
                    r.get("ms_played", 0),
                    r.get("platform"),
                    r.get("conn_country"),
                    r.get("reason_start"),
                    r.get("reason_end"),
                    int(bool(r.get("shuffle"))),
                    int(bool(r.get("skipped"))),
                    int(bool(r.get("offline"))),
                    int(bool(r.get("incognito_mode"))),
                    r.get("master_metadata_track_name"),
                    r.get("master_metadata_album_artist_name"),
                    r.get("master_metadata_album_album_name"),
                ),
            )
            inserted += 1
        except sqlite3.IntegrityError:
            # Exact duplicate (same played_at + uri + ms_played) — expected
            # when export files have overlapping date ranges (e.g. the
            # "_1" / "_2" suffixed files in your export).
            duplicates += 1

    conn.commit()
    print(f"Inserted: {inserted} new events, skipped {duplicates} duplicates")

    rebuild_track_stats(conn)
    conn.close()
    print("Done. track_listening_stats rebuilt.")


def rebuild_track_stats(conn: sqlite3.Connection) -> None:
    """Recompute track_listening_stats from scratch off listening_history."""
    cur = conn.cursor()
    cur.execute("DELETE FROM track_listening_stats")
    cur.execute(
        f"""
        INSERT INTO track_listening_stats (
            spotify_uri, play_count, total_plays_incl_skips, skip_count,
            skip_rate, total_ms_played, first_played_at, last_played_at,
            distinct_days_played, updated_at
        )
        SELECT
            spotify_uri,
            SUM(CASE WHEN ms_played > {REAL_PLAY_THRESHOLD_MS} THEN 1 ELSE 0 END) AS play_count,
            COUNT(*) AS total_plays_incl_skips,
            SUM(skipped) AS skip_count,
            CAST(SUM(skipped) AS REAL) / COUNT(*) AS skip_rate,
            SUM(ms_played) AS total_ms_played,
            MIN(played_at) AS first_played_at,
            MAX(played_at) AS last_played_at,
            COUNT(DISTINCT substr(played_at, 1, 10)) AS distinct_days_played,
            datetime('now')
        FROM listening_history
        GROUP BY spotify_uri
        """
    )
    conn.commit()


def main():
    parser = argparse.ArgumentParser(description="Import Spotify Extended Streaming History")
    parser.add_argument("--db", required=True, help="Path to your SQLite DB file")
    parser.add_argument(
        "--export", required=True,
        help="Path to the 'Spotify Extended Streaming History' folder from your export"
    )
    args = parser.parse_args()
    import_streaming_history(args.db, args.export)


if __name__ == "__main__":
    main()
    # To wire into backend/cli.py instead of running standalone:
    #   from streaming_history_importer import import_streaming_history
    #   import_streaming_history(DB_PATH, r"C:\...\Spotify Extended Streaming History")
