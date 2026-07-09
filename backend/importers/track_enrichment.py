"""
Track Enrichment Importer — Phase 2

Backfills full metadata (album, artists, duration, popularity, isrc,
preview_url) for tracks that only have a stub row (name + artist only,
from streaming_history_importer.py). These are tracks you streamed but
never liked/saved, so `import-liked` never touches them -- this importer
uses Spotify's batch GET /tracks endpoint (50 IDs per call) instead.

Also backfills the artist and album rows those tracks reference, using the
same upsert helpers as liked_songs.py so genre/album data stays consistent
across importers.

Usage:
    python -m backend.cli enrich-tracks
"""

import json
import logging
import time

import spotipy

from backend.db.database import db_conn, init_db

logger = logging.getLogger(__name__)

_BATCH_SIZE = 50  # Spotify's GET /tracks max IDs per call


def _stub_track_ids() -> list[str]:
    """Tracks with no album_id are stubs -- a real track always has an album."""
    with db_conn() as conn:
        rows = conn.execute(
            "SELECT id FROM tracks WHERE album_id IS NULL ORDER BY imported_at"
        ).fetchall()
    return [row["id"] for row in rows]


def _upsert_artist(conn, a: dict) -> None:
    conn.execute(
        """
        INSERT INTO artists (id, name, popularity, followers, image_url, spotify_url, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
        ON CONFLICT(id) DO UPDATE SET
            name=excluded.name,
