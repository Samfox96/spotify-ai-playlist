"""
Playlist Importer — Phase 4 (playlists + playlist tracks)

Imports every playlist the user owns or follows (via Spotify's
`current_user_playlists`) along with its full track listing.

Playlist API responses include full track objects (not just IDs), so this
importer upserts complete track/artist/album metadata as it goes -- tracks
discovered here don't need a separate enrichment pass like the
streaming-history stub tracks do.

Usage:
    python -m backend.cli import-playlists
"""

import json
import logging
import time

import spotipy

from backend.db.database import db_conn, init_db

logger = logging.getLogger(__name__)

_PLAYLIST_PAGE_SIZE = 50
_TRACKS_PAGE_SIZE = 100


def _upsert_artist(conn, a: dict) -> None:
    if not a or not a.get("id"):
        return
    conn.execute(
        """
        INSERT INTO artists (id, name, popularity, followers, image_url, spotify_url, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
        ON CONFLICT(id) DO UPDATE SET name=excluded.name, updated_at=datetime('now')
        """,
        (
            a["id"], a.get("name", "Unknown"), a.get("popularity"),
            (a.get("followers") or {}).get("total"),
            (a.get("images") or [{}])[0].get("url"),
            (a.get("external_urls") or {}).get("spotify"),
        ),
    )


def _upsert_album(conn, album: dict, artist_id, artist_name) -> None:
    if not album or not album.get("id"):
        return
    conn.execute(
        """
        INSERT INTO albums
            (id, name, artist_id, artist_name, album_type, release_date,
             total_tracks, image_url, spotify_url, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        ON CONFLICT(id) DO UPDATE SET name=excluded.name, updated_at=datetime('now')
        """,
        (
            album["id"], album.get("name", "Unknown"), artist_id, artist_name,
            album.get("album_type"), album.get("release_date"),
            album.get("total_tracks"),
            (album.get("images") or [{}])[0].get("ur
