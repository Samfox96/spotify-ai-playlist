"""
Streaming History Importer — Phase 2

Parses Spotify Extended Streaming History JSON export files and loads
music-listening events into the existing `play_history` table
(source='spotify_export'). Podcast/audiobook rows are skipped.

`play_history` is extended (additively) with ms_played, skipped, shuffle,
platform, reason_start, reason_end -- these come only from the export, not
the Recently Played API, so they're nullable for other sources.

Usage:
    python -m backend.cli import-history --export "path/to/Spotify Extended Streaming History"
"""

import glob
import json
import logging
import os

from backend.db.database import db_conn, init_db

logger = logging.getLogger(__name__)

_BATCH_SIZE = 1000

_EXPORT_COLUMNS = {
    "ms_played": "INTEGER",
    "skipped": "INTEGER",
    "shuffle": "INTEGER",
    "platform": "TEXT",
    "reason_start": "TEXT",
    "reason_end": "TEXT",
}


def ensure_export_columns(conn) -> None:
    """Add export-only columns to play_history if they don't already exist."""
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(play_history)")}
    for col, sql_type in _EXPORT_COLUMNS.items():
        if col not in existing:
            conn.execute(f"ALTER TABLE play_history ADD COLUMN {col} {sql_type}")
            logger.info("Added play_history.%s column", col)


def _extract_track_id(spotify_track_uri: str | None) -> str | None:
    """'spotify:track:3B3e...' -> '3B3e...' to match tracks.id (bare Spotify ID)."""
    if not spotify_track_uri:
        return None
    return spotify_track_uri.rsplit(":", 1)[-1]


def _load_export_files(export_dir: str) -> list[dict]:
    pattern = os.path.join(export_dir, "Streaming_History_Audio_*.json")
    files = sorted(glob.glob(pattern))
    if not files:
        raise FileNotFoundError(
            f"No Streaming_History_Audio_*.json files found in {export_dir}"
        )
    records = []
    for path in files:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        records.extend(data)
        logger.info("Loaded %s: %d records", os.path.basename(path), len(data))
    return records


def _stub_track_fields(record: dict) -> dict:
    """Minimal tracks row built from the export's own denormalized fields,
    for tracks streamed but never liked/saved (so play_history's foreign
    key is satisfiable without a full Spotify API lookup)."""
    return {
        "name": record.get("master_metadata_track_name") or "Unknown",
        "primary_artist_name": record.get("master_metadata_album_artist_name"),
    }


def import_streaming_history(export_dir: str) -> dict:
    init_db()
    with db_conn() as conn:
        ensure_export_columns(conn)

    records = _load_export_files(export_dir)

    music_records = [r for r in records if r.get("spotify_track_uri")]
    logger.info(
        "Music records: %d (dropped %d podcast/audiobook/empty)",
        len(music_records),
        len(records) - len(music_records),
    )

    # Plays for tracks not yet in `tracks` (e.g. streamed but never liked)
    # get a minimal stub row inserted -- name/artist only, no duration,
    # popularity, isrc, etc -- so play_history's foreign key is satisfied
    # without discarding real listening data. Existing importers use
    # INSERT-OR-UPDATE patterns, so these stubs get enriched automatically
    # if a future full-catalog import reaches the same track.
    with db_conn() as conn:
        known_ids = {row["id"] for row in conn.execute("SELECT id FROM tracks")}

    new_count = 0
    dup_count = 0
    stubbed = 0
    seen_stub_ids = set()

    with db_conn() as conn:
        for i in range(0, len(music_records), _BATCH_SIZE):
            batch = music_records[i:i + _BATCH_SIZE]
            for r in batch:
                track_id = _extract_track_id(r["spotify_track_uri"])
                if track_id not in known_ids and track_id not in seen_stub_ids:
                    stub = _stub_track_fields(r)
                    conn.execute(
                        "INSERT OR IGNORE INTO tracks (id, name, primary_artist_name) "
                        "VALUES (?, ?, ?)",
                        (track_id, stub["name"], stub["primary_artist_name"]),
                    )
                    seen_stub_ids.add(track_id)
                    stubbed += 1
                try:
                    conn.execute(
                        """
                        INSERT INTO play_history (
                            track_id, played_at, source, context_type, context_id,
                            ms_played, skipped, shuffle, platform,
                            reason_start, reason_end
                        ) VALUES (?, ?, 'spotify_export', NULL, NULL, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            track_id,
                            r["ts"],
                            r.get("ms_played", 0),
                            int(bool(r.get("skipped"))),
                            int(bool(r.get("shuffle"))),
                            r.get("platform"),
                            r.get("reason_start"),
                            r.get("reason_end"),
                        ),
                    )
                    new_count += 1
                except Exception as e:
                    if "UNIQUE constraint" in str(e):
                        dup_count += 1
                    else:
                        raise

    logger.info(
        "Inserted %d new play_history rows, %d duplicates skipped, "
        "%d tracks stubbed in (streamed but never liked/saved)",
        new_count, dup_count, stubbed,
    )
    return {"new": new_count, "duplicates": dup_count, "stubbed": stubbed}
