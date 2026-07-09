-- Migration: extend play_history for Spotify Extended Streaming History import
--
-- Additive only, per database.py's design principle ("Tables are additive —
-- never destructively alter existing columns"). play_history already exists
-- with (id, track_id, played_at, source, context_type, context_id); this adds
-- columns the export provides that the API-based sources don't.
--
-- Apply with:
--   sqlite3 data/music_intelligence.db < backend/migrations/003_play_history_export_fields.sql
-- (streaming_history_importer.py also applies this automatically if the
-- columns are missing -- see ensure_export_columns() in that file.)

ALTER TABLE play_history ADD COLUMN ms_played INTEGER;
ALTER TABLE play_history ADD COLUMN skipped INTEGER;      -- 0/1, from export's `skipped` field
ALTER TABLE play_history ADD COLUMN shuffle INTEGER;      -- 0/1
ALTER TABLE play_history ADD COLUMN platform TEXT;
ALTER TABLE play_history ADD COLUMN reason_start TEXT;
ALTER TABLE play_history ADD COLUMN reason_end TEXT;
