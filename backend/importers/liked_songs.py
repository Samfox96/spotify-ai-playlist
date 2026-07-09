"""
Liked Songs Importer.
"""

import json
import logging
import time
from typing import Generator

import spotipy

from backend.db.database import db_conn, init_db
from backend.config import config

logger = logging.getLogger(__name__)

_PAGE_SIZE = 50


def _iter_liked_songs(client, incremental=True):
    with db_conn() as conn:
        row = conn.execute(
            "SELECT liked_at FROM liked_songs ORDER BY liked_at DESC LIMIT 1"
        ).fetchone()
        newest_local = row["liked_at"] if row else None

    logger.info("Starting liked songs fetch. Incremental=%s, newest_local=%s", incremental, newest_local)

    offset = 0
    total = None

    while True:
        try:
            result = client.current_user_saved_tracks(limit=_PAGE_SIZE, offset=offset)
        except spotipy.SpotifyException as e:
            logger.error("Spotify API error at offset %d: %s", offset, e)
            raise

        if total is None:
            total = result["total"]
            logger.info("Total liked songs on Spotify: %d", total)

        items = result.get("items", [])
        if not items:
            break

        for item in items:
            added_at = item.get("added_at")
            if incremental and newest_local and added_at and added_at <= newest_local:
                logger.info("Reached already-imported tracks. Stopping early.")
                return
            yield item

        offset += len(items)
        logger.debug("Fetched %d / %d", min(offset, total), total)

        if offset >= total:
            break

        time.sleep(0.1)


def _normalise_artist(artist):
    return {
        "id": artist["id"],
        "name": artist["name"],
        "genres": json.dumps(artist.get("genres", [])),
        "popularity": artist.get("popularity"),
        "followers": artist.get("followers", {}).get("total") if artist.get("followers") else None,
        "image_url": (artist.get("images") or [{}])[0].get("url"),
        "spotify_url": artist.get("external_urls", {}).get("spotify"),
    }


def _normalise_album(album):
    artists = album.get("artists", [])
    primary = artists[0] if artists else {}
    return {
        "id": album["id"],
        "name": album["name"],
        "artist_id": primary.get("id"),
        "artist_name": primary.get("name"),
        "album_type": album.get("album_type"),
        "release_date": album.get("release_date"),
        "total_tracks": album.get("total_tracks"),
        "image_url": (album.get("images") or [{}])[0].get("url"),
        "spotify_url": album.get("external_urls", {}).get("spotify"),
        "label": album.get("label"),
    }


def _normalise_track(track):
    artists = track.get("artists", [])
    primary = artists[0] if artists else {}
    album = track.get("album", {})
    return {
        "id": track["id"],
        "name": track["name"],
        "album_id": album.get("id"),
        "artist_ids": json.dumps([a["id"] for a in artists]),
        "artist_names": json.dumps([a["name"] for a in artists]),
        "primary_artist_id": primary.get("id"),
        "primary_artist_name": primary.get("name"),
        "duration_ms": track.get("duration_ms"),
        "explicit": 1 if track.get("explicit") else 0,
        "popularity": track.get("popularity"),
        "preview_url": track.get("preview_url"),
        "spotify_url": track.get("external_urls", {}).get("spotify"),
        "isrc": track.get("external_ids", {}).get("isrc"),
    }


def _upsert_artist(conn, d):
    conn.execute("""
        INSERT INTO artists (id, name, genres, popularity, followers, image_url, spotify_url, updated_at)
        VALUES (:id, :name, :genres, :popularity, :followers, :image_url, :spotify_url, datetime('now'))
        ON CONFLICT(id) DO UPDATE SET
            name=excluded.name, genres=excluded.genres, popularity=excluded.popularity,
            followers=excluded.followers, image_url=excluded.image_url,
            spotify_url=excluded.spotify_url, updated_at=datetime('now')
    """, d)


def _upsert_album(conn, d):
    conn.execute("""
        INSERT INTO albums
            (id, name, artist_id, artist_name, album_type, release_date,
             total_tracks, image_url, spotify_url, label, updated_at)
        VALUES
            (:id, :name, :artist_id, :artist_name, :album_type, :release_date,
             :total_tracks, :image_url, :spotify_url, :label, datetime('now'))
        ON CONFLICT(id) DO UPDATE SET
            name=excluded.name, artist_name=excluded.artist_name,
            release_date=excluded.release_date, image_url=excluded.image_url,
            updated_at=datetime('now')
    """, d)


def _upsert_track(conn, d):
    conn.execute("""
        INSERT INTO tracks
            (id, name, album_id, artist_ids, artist_names, primary_artist_id,
             primary_artist_name, duration_ms, explicit, popularity,
             preview_url, spotify_url, isrc, updated_at)
        VALUES
            (:id, :name, :album_id, :artist_ids, :artist_names, :primary_artist_id,
             :primary_artist_name, :duration_ms, :explicit, :popularity,
             :preview_url, :spotify_url, :isrc, datetime('now'))
        ON CONFLICT(id) DO UPDATE SET
            name=excluded.name, popularity=excluded.popularity,
            preview_url=excluded.preview_url, updated_at=datetime('now')
    """, d)


def _upsert_liked_song(conn, track_id, liked_at):
    existing = conn.execute(
        "SELECT track_id FROM liked_songs WHERE track_id = ?", (track_id,)
    ).fetchone()

    if existing:
        return False, False

    conn.execute("""
        INSERT INTO liked_songs (track_id, liked_at)
        VALUES (?, ?)
        ON CONFLICT(track_id) DO UPDATE SET
            liked_at=excluded.liked_at, updated_at=datetime('now')
    """, (track_id, liked_at))

    return True, False


def _start_log(conn, import_type):
    cur = conn.execute(
        "INSERT INTO import_log (import_type, status) VALUES (?, 'running')", (import_type,)
    )
    return cur.lastrowid


def _finish_log(conn, log_id, found, new, updated, status="completed", error=None):
    conn.execute("""
        UPDATE import_log SET
            completed_at=datetime('now'), tracks_found=?, tracks_new=?,
            tracks_updated=?, status=?, error_message=?
        WHERE id=?
    """, (found, new, updated, status, error, log_id))


def import_liked_songs(client, incremental=True, batch_size=200):
    init_db()

    counts = {"found": 0, "new": 0, "updated": 0, "errors": 0}
    log_id = None

    try:
        with db_conn() as conn:
            log_id = _start_log(conn, "liked_songs")

        batch_artists = {}
        batch_albums = {}
        batch_tracks = []
        batch_liked = []

        def _flush_batch():
            with db_conn() as conn:
                # Disable foreign keys during import to avoid ordering issues
                conn.execute("PRAGMA foreign_keys=OFF")

                for a in batch_artists.values():
                    _upsert_artist(conn, a)
                for al in batch_albums.values():
                    _upsert_album(conn, al)
                for t in batch_tracks:
                    _upsert_track(conn, t)
                for track_id, liked_at in batch_liked:
                    is_new, is_updated = _upsert_liked_song(conn, track_id, liked_at)
                    if is_new:
                        counts["new"] += 1
                    elif is_updated:
                        counts["updated"] += 1

            batch_artists.clear()
            batch_albums.clear()
            batch_tracks.clear()
            batch_liked.clear()

        for item in _iter_liked_songs(client, incremental=incremental):
            track = item.get("track")
            if not track or not track.get("id"):
                continue

            counts["found"] += 1

            try:
                for artist in track.get("artists", []):
                    if artist.get("id") and artist["id"] not in batch_artists:
                        batch_artists[artist["id"]] = _normalise_artist(artist)

                album = track.get("album", {})
                if album.get("id") and album["id"] not in batch_albums:
                    batch_albums[album["id"]] = _normalise_album(album)

                batch_tracks.append(_normalise_track(track))
                batch_liked.append((track["id"], item.get("added_at", "")))

            except (KeyError, TypeError) as e:
                logger.warning("Error processing track %s: %s", track.get("id"), e)
                counts["errors"] += 1
                continue

            if counts["found"] % batch_size == 0:
                _flush_batch()
                logger.info("Progress: %d tracks processed (%d new)", counts["found"], counts["new"])

        if batch_liked:
            _flush_batch()

        with db_conn() as conn:
            _finish_log(conn, log_id, counts["found"], counts["new"], counts["updated"])

        logger.info(
            "Import complete. Found=%d New=%d Updated=%d Errors=%d",
            counts["found"], counts["new"], counts["updated"], counts["errors"],
        )
        return counts

    except Exception as e:
        logger.error("Import failed: %s", e)
        if log_id:
            with db_conn() as conn:
                _finish_log(conn, log_id, counts["found"], counts["new"], counts["updated"],
                            status="failed", error=str(e))
        raise