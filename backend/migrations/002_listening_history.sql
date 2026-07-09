-- Migration 002: Listening History (Phase 2)
-- Adds raw listening event storage + derived per-track aggregate stats,
-- sourced from the Spotify Extended Streaming History export.

-- Raw, deduplicated playback events. This is the ground-truth data.
-- One row per (ts, spotify_uri, ms_played) — Spotify's export can contain
-- exact duplicate rows across overlapping export files, so we dedupe on
-- that natural key at insert time.
CREATE TABLE IF NOT EXISTS listening_history (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    played_at           TEXT NOT NULL,          -- ISO8601 UTC timestamp ('ts' field)
    spotify_uri         TEXT NOT NULL,           -- spotify:track:...
    ms_played           INTEGER NOT NULL,
    platform            TEXT,
    conn_country        TEXT,
    reason_start        TEXT,
    reason_end          TEXT,
    shuffle             INTEGER,                 -- 0/1
    skipped             INTEGER,                 -- 0/1
    offline             INTEGER,                  -- 0/1
    incognito_mode      INTEGER,                 -- 0/1
    -- denormalized metadata as a fallback for tracks Spotify has since
    -- delisted / renamed, so history remains readable even without a match
    track_name          TEXT,
    artist_name         TEXT,
    album_name          TEXT,
    imported_at         TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (played_at, spotify_uri, ms_played)
);

CREATE INDEX IF NOT EXISTS idx_listening_history_uri ON listening_history (spotify_uri);
CREATE INDEX IF NOT EXISTS idx_listening_history_played_at ON listening_history (played_at);

-- Derived per-track aggregates. Rebuilt (not incrementally updated) each
-- time new history is imported — see `rebuild_track_stats()` in the importer.
-- NOTE: joins to your `tracks` table via spotify_uri. If your tracks table
-- uses a different column name for the Spotify URI, update TRACKS_URI_COLUMN
-- in streaming_history_importer.py and this table stays unaffected (it's
-- populated from listening_history directly, then the app layer can join
-- track_listening_stats.spotify_uri -> tracks.<your_uri_column>).
CREATE TABLE IF NOT EXISTS track_listening_stats (
    spotify_uri         TEXT PRIMARY KEY,
    play_count          INTEGER NOT NULL DEFAULT 0,      -- ms_played > 30000 (a "real" play)
    total_plays_incl_skips INTEGER NOT NULL DEFAULT 0,   -- every logged event, including skips
    skip_count          INTEGER NOT NULL DEFAULT 0,
    skip_rate           REAL NOT NULL DEFAULT 0,          -- skip_count / total_plays_incl_skips
    total_ms_played     INTEGER NOT NULL DEFAULT 0,
    first_played_at     TEXT,
    last_played_at      TEXT,
    distinct_days_played INTEGER NOT NULL DEFAULT 0,
    updated_at          TEXT NOT NULL DEFAULT (datetime('now'))
);
