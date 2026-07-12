"""
Playlist Export Importer — workaround for Spotify's Extended Quota Mode block

The live API's playlist_items() endpoint is currently gated behind Extended
Quota Mode approval (see playlists.py). But Spotify's own "Account Data"
GDPR export (distinct from "Extended Streaming History") includes full
playlist contents -- track name, artist, album, and Spotify URI -- for every
playlist you own. This importer reads that export directly, sidestepping
the API restriction entirely.

Only OWNED playlists appear in this export (not ones you follow but didn't
create) -- that's a limitation of Spotify's export, not this importer.

Note: this export format doesn't include real Spotify playlist IDs (only
names), so a stable pseudo-ID is derived from each playlist's name
(source='export' distinguishes these from API-imported playlists, which use
real Spotify IDs and source='api').

Usage:
    python -m backend.cli import-playlists-export --export "path/to/Spotify Account Data"
"""

import glob
import hashlib
import json
import logging
import os

from backend.db.database import db_conn, init_db

logger = logging.getLogger(__name__)


def ensure_source_column(conn) -> None:
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(playlists)")}
    if "source" not in existing:
        conn.execute("ALTER TABLE playlists ADD COLUMN source TEXT DEFAULT 'api'")
        logger.info("Added playlists.source column")


def _pseudo_playlist_id(name: str) -> str:
    """Stable id derived from playlist name, since this export has no real
    Spotify playlist ID. 'export:' prefix keeps it visually distinct from
    real Spotify IDs used by the API-based importer."""
    digest = hashlib.sha1(name.encode("utf-8")).hexdigest()[:16]
    return f"export:{digest}"


def _extract_track_id(track_uri: str | None) -> str | None:
    if not track_uri:
        return None
    return track_uri.rsplit(":", 1)[-1]


def _load_export_playlists(export_dir: str) -> list[dict]:
    pattern = os.path.join(export_dir, "Playlist*.json")
    files = sorted(glob.glob(pattern))
    if not files:
        raise FileNotFoundError(
            f"No Playlist*.json files found in {export_dir}. "
            "Point --export at the 'Spotify Account Data' folder from your export."
        )
    playlists = []
    for path in files:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        playlists.extend(data.get("playlists", []))
        logger.info("Loaded %s: %d playlists", os.path.basename(path), len(data.get("playlists", [])))
    return playlists


def import_playlists_from_export(export_dir: str) -> dict:
    init_db()
    with db_conn() as conn:
        ensure_source_column(conn)

    playlists = _load_export_playlists(export_dir)
    logger.info("Total playlists in export: %d", len(playlists))

    counts = {
        "playlists": 0, "tracks_seen": 0, "tracks_linked": 0,
        "tracks_stubbed": 0, "skipped_non_track": 0,
    }

    with db_conn() as conn:
        known_ids = {row["id"] for row in conn.execute("SELECT id FROM tracks")}

    for pl in playlists:
        name = pl.get("name") or "Untitled"
        pl_id = _pseudo_playlist_id(name)
        items = pl.get("items", [])

        with db_conn() as conn:
            conn.execute(
                """
                INSERT INTO playlists (id, name, total_tracks, source, updated_at)
                VALUES (?, ?, ?, 'export', datetime('now'))
                ON CONFLICT(id) DO UPDATE SET
                    total_tracks=excluded.total_tracks, updated_at=datetime('now')
                """,
                (pl_id, name, len(items)),
            )
        counts["playlists"] += 1

        with db_conn() as conn:
            for position, item in enumerate(items):
                counts["tracks_seen"] += 1
                track = item.get("track")
                if not track or not track.get("trackUri"):
                    counts["skipped_non_track"] += 1
                    continue

                track_id = _extract_track_id(track["trackUri"])
                if track_id not in known_ids:
                    conn.execute(
                        "INSERT OR IGNORE INTO tracks (id, name, primary_artist_name) VALUES (?, ?, ?)",
                        (track_id, track.get("trackName", "Unknown"), track.get("artistName")),
                    )
                    known_ids.add(track_id)
                    counts["tracks_stubbed"] += 1

                conn.execute(
                    """
                    INSERT INTO playlist_tracks (playlist_id, track_id, added_at, position)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(playlist_id, track_id) DO UPDATE SET
                        added_at=excluded.added_at, position=excluded.position
                    """,
                    (pl_id, track_id, item.get("addedDate"), position),
                )
                counts["tracks_linked"] += 1

    logger.info("Playlist export import done: %s", counts)
    return counts
