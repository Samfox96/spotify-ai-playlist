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
            name=excluded.name, popularity=excluded.popularity,
            followers=excluded.followers, image_url=excluded.image_url,
            spotify_url=excluded.spotify_url, updated_at=datetime('now')
        """,
        (
            a["id"], a["name"], a.get("popularity"),
            a.get("followers", {}).get("total"),
            (a.get("images") or [{}])[0].get("url"),
            a.get("external_urls", {}).get("spotify"),
        ),
    )
    # NOTE: genres come from the separate /artists endpoint (artists.py's
    # import_artist_genres), not from a track lookup -- Spotify's track
    # response doesn't include artist genres. Run import-artists afterward
    # if these newly-discovered artists need genre data too.


def _upsert_album(conn, album: dict, artist_id: str | None, artist_name: str | None) -> None:
    conn.execute(
        """
        INSERT INTO albums
            (id, name, artist_id, artist_name, album_type, release_date,
             total_tracks, image_url, spotify_url, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        ON CONFLICT(id) DO UPDATE SET
            name=excluded.name, release_date=excluded.release_date,
            image_url=excluded.image_url, updated_at=datetime('now')
        """,
        (
            album["id"], album["name"], artist_id, artist_name,
            album.get("album_type"), album.get("release_date"),
            album.get("total_tracks"),
            (album.get("images") or [{}])[0].get("url"),
            album.get("external_urls", {}).get("spotify"),
        ),
    )


def _full_upsert_track(conn, track: dict) -> None:
    """Unlike liked_songs.py's _upsert_track, this overwrites album/artist
    fields too -- appropriate here since we're deliberately filling in a
    stub row for the first time, not risking clobbering good existing data."""
    artists = track.get("artists", [])
    primary = artists[0] if artists else {}
    album = track.get("album", {})
    conn.execute(
        """
        UPDATE tracks SET
            name = ?, album_id = ?, artist_ids = ?, artist_names = ?,
            primary_artist_id = ?, primary_artist_name = ?, duration_ms = ?,
            explicit = ?, popularity = ?, preview_url = ?, spotify_url = ?,
            isrc = ?, updated_at = datetime('now')
        WHERE id = ?
        """,
        (
            track["name"], album.get("id"),
            json.dumps([a["id"] for a in artists]),
            json.dumps([a["name"] for a in artists]),
            primary.get("id"), primary.get("name"),
            track.get("duration_ms"), 1 if track.get("explicit") else 0,
            track.get("popularity"), track.get("preview_url"),
            track.get("external_urls", {}).get("spotify"),
            track.get("external_ids", {}).get("isrc"),
            track["id"],
        ),
    )


def _stub_track_fields(record: dict) -> dict:
    """Minimal tracks row built from the export's own denormalized fields,
    for tracks streamed but never liked/saved (so play_history's foreign
    key is satisfiable without a full Spotify API lookup)."""
    return {
        "name": record.get("master_metadata_track_name") or "Unknown",
        "primary_artist_name": record.get("master_metadata_album_artist_name"),
    }


def enrich_stub_tracks(client: spotipy.Spotify) -> dict:
    init_db()
    ids = _stub_track_ids()
    logger.info("Stub tracks needing enrichment: %d", len(ids))

    counts = {"processed": 0, "enriched": 0, "errors": 0}

    for i in range(0, len(ids), _BATCH_SIZE):
        batch = ids[i:i + _BATCH_SIZE]
        try:
            result = client.tracks(batch)
        except spotipy.SpotifyException as e:
            if e.http_status == 403:
                logger.error(
                    "403 Forbidden on tracks endpoint -- this means Spotify "
                    "Extended Quota Mode isn't approved yet for your app. "
                    "Stopping now instead of retrying every batch. This will "
                    "start working once Spotify approves the quota request; "
                    "no code change needed, just re-run this command later."
                )
                counts["errors"] += len(ids) - i
                break
            logger.error("API error on batch: %s", e)
            counts["errors"] += len(batch)
            time.sleep(1)
            continue

        with db_conn() as conn:
            for track in result.get("tracks", []):
                counts["processed"] += 1
                if track is None:
                    # Track no longer exists on Spotify (removed/region-locked)
                    counts["errors"] += 1
                    continue
                try:
                    for artist in track.get("artists", []):
                        # Track response only has id/name/external_urls for
                        # artists -- fine, import-artists backfills genres later
                        _upsert_artist(conn, artist)
                    album = track.get("album")
                    if album:
                        primary = (track.get("artists") or [{}])[0]
                        _upsert_album(conn, album, primary.get("id"), primary.get("name"))
                    _full_upsert_track(conn, track)
                    counts["enriched"] += 1
                except Exception as e:
                    logger.warning("Failed to enrich %s: %s", track.get("id"), e)
                    counts["errors"] += 1
        time.sleep(0.1)

    logger.info("Enrichment done: %s", counts)
    return counts
