import logging
import time
import spotipy
from backend.db.database import db_conn, init_db

logger = logging.getLogger(__name__)
_BATCH_SIZE = 100

def _iter_tracks_without_features(batch_size=_BATCH_SIZE):
    with db_conn() as conn:
        rows = conn.execute("""
            SELECT t.id FROM tracks t
            LEFT JOIN audio_features af ON t.id = af.track_id
            WHERE af.track_id IS NULL
            ORDER BY t.imported_at DESC
        """).fetchall()
    track_ids = [row["id"] for row in rows]
    logger.info("Tracks needing audio features: %d", len(track_ids))
    for i in range(0, len(track_ids), batch_size):
        yield track_ids[i:i + batch_size]

def _upsert_features(conn, features):
    conn.execute("""
        INSERT INTO audio_features
            (track_id, danceability, energy, key, loudness, mode,
             speechiness, acousticness, instrumentalness, liveness,
             valence, tempo, time_signature, fetched_at)
        VALUES
            (:id, :danceability, :energy, :key, :loudness, :mode,
             :speechiness, :acousticness, :instrumentalness, :liveness,
             :valence, :tempo, :time_signature, datetime('now'))
        ON CONFLICT(track_id) DO UPDATE SET
            danceability=excluded.danceability,
            energy=excluded.energy,
            valence=excluded.valence,
            tempo=excluded.tempo,
            fetched_at=datetime('now')
    """, features)

def import_audio_features(client: spotipy.Spotify) -> dict:
    init_db()
    counts = {"processed": 0, "success": 0, "unavailable": 0, "errors": 0}
    for batch in _iter_tracks_without_features():
        try:
            results = client.audio_features(tracks=batch)
        except spotipy.SpotifyException as e:
            logger.error("API error: %s", e)
            counts["errors"] += len(batch)
            time.sleep(1)
            continue
        with db_conn() as conn:
            for features in results or []:
                counts["processed"] += 1
                if features is None:
                    counts["unavailable"] += 1
                    continue
                try:
                    _upsert_features(conn, features)
                    counts["success"] += 1
                except Exception as e:
                    logger.warning("Failed for %s: %s", features.get("id"), e)
                    counts["errors"] += 1
        time.sleep(0.1)
    logger.info("Audio features done: %s", counts)
    return counts