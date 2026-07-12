-- Migration: distinguish playlists imported from the API vs from the
-- Spotify Account Data export (which lacks real playlist IDs and is used
-- as a workaround while Extended Quota Mode is pending).
--
-- Applied automatically by playlist_export_importer.py if missing --
-- this file is here for reference / manual application if needed:
--   sqlite3 data/music_intelligence.db < backend/migrations/004_playlist_source.sql

ALTER TABLE playlists ADD COLUMN source TEXT DEFAULT 'api';
