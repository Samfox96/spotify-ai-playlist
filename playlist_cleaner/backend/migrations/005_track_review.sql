-- Migration: decouple review status from liked_songs
--
-- Review status/notes previously lived only on liked_songs, meaning only
-- liked tracks could ever enter the review workflow. This breaks that
-- coupling: any track (liked, in a playlist, or just heavily streamed) can
-- now be reviewed. Existing review decisions on liked_songs are copied
-- over so no prior curation work is lost.
--
-- liked_songs.review_status/review_notes/reviewed_at are left in place
-- (not dropped) for backward compatibility with anything still reading
-- them directly -- they simply stop being written to going forward.

CREATE TABLE IF NOT EXISTS track_review (
    track_id            TEXT PRIMARY KEY,
    review_status       TEXT NOT NULL DEFAULT 'unreviewed',
        -- unreviewed | love | keep | archive_candidate | skip | archived | deleted
    review_notes        TEXT,
    reviewed_at          TEXT,
    last_shown_in_queue  TEXT,
    created_at           TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at           TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (track_id) REFERENCES tracks(id)
);

CREATE INDEX IF NOT EXISTS idx_track_review_status ON track_review(review_status);

-- Carry over existing review decisions (only actual decisions, not the
-- default 'unreviewed' placeholder -- absence of a row already means
-- unreviewed under the new model).
INSERT OR IGNORE INTO track_review (track_id, review_status, review_notes, reviewed_at, last_shown_in_queue, created_at, updated_at)
SELECT track_id, review_status, review_notes, reviewed_at, last_shown_in_queue, imported_at, updated_at
FROM liked_songs
WHERE review_status IS NOT NULL AND review_status != 'unreviewed';
