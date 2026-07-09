"""
Artist Enrichment Importer.

Fetches full artist data (including genres) for all artists in the DB
that have empty or missing genre data.

Spotify's track endpoint doesn't return genres — only the artist endpoint does.
This runs as a separate job after liked_songs import.
"""

import json
import logging
import time

import spotipy

from backend.db.database import db_conn, init_db

logger = logging.getLogger(__name__)

_BATCH_SIZE = 50  # Spotify artist endpoint max


def import_artist_genres(client: spotipy.Spotify) -> dict:
    """
    Fetch full artist data including genres for all artists missing them.
    """
    init_db()
    counts = {"processed": 0, "updated": 0, "errors": 0}

    # Get all artists with missing/empty genres
    with db_conn() as conn:
        rows = conn.execute("""
            SELECT id FROM artists
            WHERE genres IS NULL OR genres = '[]' OR genres = ''
            ORDER BY id
        """).fetchall()

    artist_ids = [r["id"] for r in rows]
    logger.info("Artists needing genre data: %d", len(artist_ids))

    if not artist_ids:
        logger.info("All artists already have genre data.")
        return counts

    # Process in batches of 50
    for i in range(0, len(artist_ids), _BATCH_SIZE):
        batch = artist_ids[i:i + _BATCH_SIZE]
        try:
            results = client.artists(batch)
            artists = results.get("artists", [])
        except spotipy.SpotifyException as e:
            logger.error("API error fetching artists batch: %s", e)
            counts["errors"] += len(batch)
            time.sleep(1)
            continue

        with db_conn() as conn:
            for artist in artists or []:
                if not artist:
                    continue
                counts["processed"] += 1
                try:
                    genres = json.dumps(artist.get("genres", []))
                    followers = artist.get("followers", {}).get("total") if artist.get("followers") else None
                    image_url = (artist.get("images") or [{}])[0].get("url")

                    conn.execute("""
                        UPDATE artists SET
                            genres     = ?,
                            popularity = ?,
                            followers  = ?,
                            image_url  = ?,
                            updated_at = datetime('now')
                        WHERE id = ?
                    """, (genres, artist.get("popularity"), followers, image_url, artist["id"]))
                    counts["updated"] += 1
                except Exception as e:
                    logger.warning("Failed to update artist %s: %s", artist.get("id"), e)
                    counts["errors"] += 1

        logger.debug("Artist enrichment: %d / %d processed", min(i + _BATCH_SIZE, len(artist_ids)), len(artist_ids))
        time.sleep(0.1)

    logger.info("Artist enrichment done: %d updated, %d errors", counts["updated"], counts["errors"])
    return counts
