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
            (album.get("images") or [{}])[0].get("url"),
            (album.get("external_urls") or {}).get("spotify"),
        ),
    )


def _upsert_track(conn, track: dict) -> None:
    artists = track.get("artists") or []
    primary = artists[0] if artists else {}
    album = track.get("album") or {}
    conn.execute(
        """
        INSERT INTO tracks
            (id, name, album_id, artist_ids, artist_names, primary_artist_id,
             primary_artist_name, duration_ms, explicit, popularity,
             preview_url, spotify_url, isrc, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        ON CONFLICT(id) DO UPDATE SET
            name=excluded.name, popularity=excluded.popularity, updated_at=datetime('now')
        """,
        (
            track["id"], track.get("name", "Unknown"), album.get("id"),
            json.dumps([a["id"] for a in artists if a.get("id")]),
            json.dumps([a.get("name", "Unknown") for a in artists]),
            primary.get("id"), primary.get("name"),
            track.get("duration_ms"), 1 if track.get("explicit") else 0,
            track.get("popularity"), track.get("preview_url"),
            (track.get("external_urls") or {}).get("spotify"),
            (track.get("external_ids") or {}).get("isrc"),
        ),
    )


def _upsert_playlist(conn, pl: dict) -> None:
    owner = pl.get("owner") or {}
    conn.execute(
        """
        INSERT INTO playlists
            (id, name, description, owner_id, is_public, collaborative,
             total_tracks, snapshot_id, image_url, spotify_url, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        ON CONFLICT(id) DO UPDATE SET
            name=excluded.name, total_tracks=excluded.total_tracks,
            snapshot_id=excluded.snapshot_id, image_url=excluded.image_url,
            updated_at=datetime('now')
        """,
        (
            pl["id"], pl.get("name", "Untitled"), pl.get("description"),
            owner.get("id"), 1 if pl.get("public") else 0,
            1 if pl.get("collaborative") else 0,
            (pl.get("tracks") or {}).get("total"),
            pl.get("snapshot_id"),
            (pl.get("images") or [{}])[0].get("url"),
            (pl.get("external_urls") or {}).get("spotify"),
        ),
    )


def _upsert_playlist_track(conn, playlist_id, track_id, added_at, added_by, position) -> None:
    conn.execute(
        """
        INSERT INTO playlist_tracks (playlist_id, track_id, added_at, added_by, position)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(playlist_id, track_id) DO UPDATE SET
            added_at=excluded.added_at, position=excluded.position
        """,
        (playlist_id, track_id, added_at, added_by, position),
    )


def import_playlists(client: spotipy.Spotify) -> dict:
    init_db()
    counts = {
        "playlists": 0, "tracks_seen": 0, "tracks_new_or_updated": 0,
        "skipped_non_track": 0, "errors": 0,
    }

    results = client.current_user_playlists(limit=_PLAYLIST_PAGE_SIZE)
    playlists = []
    while results:
        playlists.extend(results.get("items", []))
        results = client.next(results) if results.get("next") else None

    logger.info("Found %d playlists", len(playlists))

    for pl in playlists:
        if not pl or not pl.get("id"):
            continue
        try:
            with db_conn() as conn:
                _upsert_playlist(conn, pl)
            counts["playlists"] += 1

            position = 0
            items_page = client.playlist_items(pl["id"], limit=_TRACKS_PAGE_SIZE)
            while items_page:
                with db_conn() as conn:
                    for item in items_page.get("items", []):
                        track = item.get("track")
                        counts["tracks_seen"] += 1
                        is_track_type = (track or {}).get("type", "track") == "track"
                        if not track or not track.get("id") or track.get("is_local") or not is_track_type:
                            counts["skipped_non_track"] += 1
                            position += 1
                            continue
                        try:
                            for artist in track.get("artists") or []:
                                _upsert_artist(conn, artist)
                            album = track.get("album")
                            if album:
                                primary = (track.get("artists") or [{}])[0]
                                _upsert_album(conn, album, primary.get("id"), primary.get("name"))
                            _upsert_track(conn, track)
                            added_by = (item.get("added_by") or {}).get("id")
                            _upsert_playlist_track(
                                conn, pl["id"], track["id"], item.get("added_at"), added_by, position
                            )
                            counts["tracks_new_or_updated"] += 1
                        except Exception as e:
                            logger.warning("Failed track in playlist %s: %s", pl.get("name"), e)
                            counts["errors"] += 1
                        position += 1
                items_page = client.next(items_page) if items_page.get("next") else None
            time.sleep(0.05)
        except spotipy.SpotifyException as e:
            logger.error("Failed to import playlist %s: %s", pl.get("name"), e)
            counts["errors"] += 1
            time.sleep(0.5)

    logger.info("Playlist import done: %s", counts)
    return counts
