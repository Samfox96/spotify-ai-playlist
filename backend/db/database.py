"""
Database connection and schema management.

Design principles:
- All data stored locally. Spotify is a source, not the owner.
- Schema is versioned via user_version pragma.
- Columns are nullable where data may be unavailable (e.g. play counts).
- Tables are additive — never destructively alter existing columns.
"""

import sqlite3
import logging
from pathlib import Path
from contextlib import contextmanager
from typing import Generator

from backend.config import config

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    """Return a configured SQLite connection."""
    path = db_path or config.DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row       # Access columns by name
    conn.execute("PRAGMA journal_mode=WAL")   # Better concurrent reads
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


@contextmanager
def db_conn(db_path: Path | None = None) -> Generator[sqlite3.Connection, None, None]:
    """Context manager — commits on success, rolls back on error."""
    conn = get_connection(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

SCHEMA_SQL = """
-- ── Artists ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS artists (
    id                  TEXT PRIMARY KEY,   -- Spotify artist ID
    name                TEXT NOT NULL,
    genres              TEXT,               -- JSON array
    popularity          INTEGER,            -- 0-100, Spotify
    followers           INTEGER,
    image_url           TEXT,
    spotify_url         TEXT,
    imported_at         TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ── Albums ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS albums (
    id                  TEXT PRIMARY KEY,   -- Spotify album ID
    name                TEXT NOT NULL,
    artist_id           TEXT,               -- Primary artist
    artist_name         TEXT,               -- Denormalised for speed
    album_type          TEXT,               -- album / single / compilation
    release_date        TEXT,
    total_tracks        INTEGER,
    image_url           TEXT,
    spotify_url         TEXT,
    label               TEXT,
    imported_at         TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at          TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (artist_id) REFERENCES artists(id)
);

-- ── Tracks ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS tracks (
    id                  TEXT PRIMARY KEY,   -- Spotify track ID
    name                TEXT NOT NULL,
    album_id            TEXT,
    artist_ids          TEXT,               -- JSON array (all artists)
    artist_names        TEXT,               -- JSON array (denormalised)
    primary_artist_id   TEXT,
    primary_artist_name TEXT,
    duration_ms         INTEGER,
    explicit            INTEGER DEFAULT 0,  -- boolean
    popularity          INTEGER,            -- 0-100
    preview_url         TEXT,
    spotify_url         TEXT,
    isrc                TEXT,               -- International Standard Recording Code
    imported_at         TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at          TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (album_id)          REFERENCES albums(id),
    FOREIGN KEY (primary_artist_id) REFERENCES artists(id)
);

-- ── Audio Features ────────────────────────────────────────────────────────
-- Stored separately: may be unavailable, fetched in bulk, updated independently
CREATE TABLE IF NOT EXISTS audio_features (
    track_id            TEXT PRIMARY KEY,
    danceability        REAL,   -- 0.0-1.0
    energy              REAL,   -- 0.0-1.0
    key                 INTEGER, -- 0-11 (Pitch Class)
    loudness            REAL,   -- dB
    mode                INTEGER, -- 0 minor, 1 major
    speechiness         REAL,
    acousticness        REAL,
    instrumentalness    REAL,
    liveness            REAL,
    valence             REAL,   -- 0.0=sad, 1.0=happy
    tempo               REAL,   -- BPM
    time_signature      INTEGER,
    fetched_at          TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (track_id) REFERENCES tracks(id)
);

-- ── Liked Songs ───────────────────────────────────────────────────────────
-- The user's Spotify library. Central table for curation.
CREATE TABLE IF NOT EXISTS liked_songs (
    track_id            TEXT PRIMARY KEY,
    liked_at            TEXT,               -- When user liked it on Spotify
    review_status       TEXT DEFAULT 'unreviewed',
        -- unreviewed | love | keep | archive_candidate | archived | deleted
    review_notes        TEXT,               -- User's personal notes
    reviewed_at         TEXT,
    last_shown_in_queue TEXT,               -- When it appeared in review queue
    imported_at         TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at          TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (track_id) REFERENCES tracks(id)
);

-- ── Playlists ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS playlists (
    id                  TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    description         TEXT,
    owner_id            TEXT,
    is_public           INTEGER DEFAULT 0,
    collaborative       INTEGER DEFAULT 0,
    total_tracks        INTEGER,
    snapshot_id         TEXT,               -- Spotify version fingerprint
    image_url           TEXT,
    spotify_url         TEXT,
    imported_at         TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ── Playlist Tracks ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS playlist_tracks (
    playlist_id         TEXT NOT NULL,
    track_id            TEXT NOT NULL,
    added_at            TEXT,
    added_by            TEXT,
    position            INTEGER,
    PRIMARY KEY (playlist_id, track_id),
    FOREIGN KEY (playlist_id) REFERENCES playlists(id),
    FOREIGN KEY (track_id)    REFERENCES tracks(id)
);

-- ── Play History ──────────────────────────────────────────────────────────
-- Populated from Recently Played API, Spotify Export, Last.fm, etc.
CREATE TABLE IF NOT EXISTS play_history (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    track_id            TEXT NOT NULL,
    played_at           TEXT NOT NULL,      -- ISO8601 UTC
    source              TEXT NOT NULL,      -- spotify_api | spotify_export | lastfm | manual
    context_type        TEXT,               -- playlist | album | artist | unknown
    context_id          TEXT,
    UNIQUE (track_id, played_at, source),
    FOREIGN KEY (track_id) REFERENCES tracks(id)
);

-- ── Import Log ────────────────────────────────────────────────────────────
-- Audit trail for every import run
CREATE TABLE IF NOT EXISTS import_log (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    import_type         TEXT NOT NULL,      -- liked_songs | playlists | audio_features | history
    started_at          TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at        TEXT,
    tracks_found        INTEGER DEFAULT 0,
    tracks_new          INTEGER DEFAULT 0,
    tracks_updated      INTEGER DEFAULT 0,
    status              TEXT DEFAULT 'running', -- running | completed | failed
    error_message       TEXT,
    metadata            TEXT                -- JSON for extra context
);

-- ── Indexes ───────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_liked_songs_status    ON liked_songs(review_status);
CREATE INDEX IF NOT EXISTS idx_liked_songs_liked_at  ON liked_songs(liked_at);
CREATE INDEX IF NOT EXISTS idx_tracks_artist         ON tracks(primary_artist_id);
CREATE INDEX IF NOT EXISTS idx_tracks_album          ON tracks(album_id);
CREATE INDEX IF NOT EXISTS idx_play_history_track    ON play_history(track_id);
CREATE INDEX IF NOT EXISTS idx_play_history_played   ON play_history(played_at);
CREATE INDEX IF NOT EXISTS idx_playlist_tracks_pl    ON playlist_tracks(playlist_id);
"""


def init_db(db_path: Path | None = None) -> None:
    """Create all tables if they don't exist. Safe to call repeatedly."""
    with db_conn(db_path) as conn:
        current_version = conn.execute("PRAGMA user_version").fetchone()[0]

        if current_version == 0:
            logger.info("Initialising database schema (v%d)...", SCHEMA_VERSION)
            conn.executescript(SCHEMA_SQL)
            conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            logger.info("Database ready at: %s", db_path or config.DB_PATH)
        elif current_version < SCHEMA_VERSION:
            logger.info(
                "Schema migration needed: v%d → v%d (not yet implemented)",
                current_version,
                SCHEMA_VERSION,
            )
        else:
            logger.debug("Database schema up to date (v%d)", current_version)
