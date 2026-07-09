"""
Flask API server - with Review Queue endpoints.
"""

import logging
from flask import Flask, jsonify, request
from flask_cors import CORS

from backend.config import config
from backend.db.database import init_db, db_conn
from backend.auth.spotify_auth import get_spotify_client, get_current_user
from backend.importers.liked_songs import import_liked_songs
from backend.importers.audio_features import import_audio_features

logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = config.FLASK_SECRET_KEY
CORS(app, origins=["http://localhost:3000", "http://localhost:5173"])


@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "version": "0.1.0"})


@app.route("/api/auth/status")
def auth_status():
    try:
        client = get_spotify_client()
        user = get_current_user(client)
        return jsonify({"authenticated": True, "user": user})
    except Exception as e:
        return jsonify({"authenticated": False, "error": str(e)}), 401


@app.route("/api/import/liked-songs", methods=["POST"])
def trigger_liked_songs_import():
    incremental = request.json.get("incremental", True) if request.json else True
    try:
        client = get_spotify_client()
        counts = import_liked_songs(client, incremental=incremental)
        return jsonify({"status": "completed", "counts": counts})
    except Exception as e:
        return jsonify({"status": "failed", "error": str(e)}), 500


@app.route("/api/import/audio-features", methods=["POST"])
def trigger_audio_features_import():
    try:
        client = get_spotify_client()
        counts = import_audio_features(client)
        return jsonify({"status": "completed", "counts": counts})
    except Exception as e:
        return jsonify({"status": "failed", "error": str(e)}), 500


@app.route("/api/import/history")
def import_history():
    with db_conn() as conn:
        rows = conn.execute("SELECT * FROM import_log ORDER BY started_at DESC LIMIT 20").fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/library/stats")
def library_stats():
    with db_conn() as conn:
        total_liked = conn.execute("SELECT COUNT(*) as n FROM liked_songs").fetchone()["n"]
        by_status = conn.execute("SELECT review_status, COUNT(*) as n FROM liked_songs GROUP BY review_status").fetchall()
        total_artists = conn.execute("SELECT COUNT(*) as n FROM artists").fetchone()["n"]
        total_albums = conn.execute("SELECT COUNT(*) as n FROM albums").fetchone()["n"]
        with_features = conn.execute("SELECT COUNT(*) as n FROM audio_features").fetchone()["n"]
        oldest = conn.execute("SELECT liked_at FROM liked_songs ORDER BY liked_at ASC LIMIT 1").fetchone()
        newest = conn.execute("SELECT liked_at FROM liked_songs ORDER BY liked_at DESC LIMIT 1").fetchone()
    return jsonify({
        "total_liked": total_liked,
        "total_artists": total_artists,
        "total_albums": total_albums,
        "with_audio_features": with_features,
        "by_review_status": {row["review_status"]: row["n"] for row in by_status},
        "oldest_liked_at": oldest["liked_at"] if oldest else None,
        "newest_liked_at": newest["liked_at"] if newest else None,
    })


@app.route("/api/library/liked-songs")
def liked_songs():
    page = int(request.args.get("page", 1))
    page_size = int(request.args.get("page_size", 50))
    status = request.args.get("status")
    offset = (page - 1) * page_size
    where = "WHERE ls.review_status = ?" if status else ""
    params = [status, page_size, offset] if status else [page_size, offset]
    with db_conn() as conn:
        rows = conn.execute(f"""
            SELECT ls.track_id, ls.liked_at, ls.review_status,
                t.name, t.primary_artist_name, t.duration_ms, t.popularity, t.spotify_url,
                al.name AS album_name, al.release_date, al.image_url AS album_image,
                af.energy, af.valence, af.tempo, af.danceability
            FROM liked_songs ls
            JOIN tracks t ON ls.track_id = t.id
            LEFT JOIN albums al ON t.album_id = al.id
            LEFT JOIN audio_features af ON ls.track_id = af.track_id
            {where}
            ORDER BY ls.liked_at DESC LIMIT ? OFFSET ?
        """, params).fetchall()
        total = conn.execute(f"SELECT COUNT(*) as n FROM liked_songs ls {where}", [status] if status else []).fetchone()["n"]
    return jsonify({"total": total, "page": page, "page_size": page_size, "tracks": [dict(r) for r in rows]})


@app.route("/api/review/queue")
def review_queue():
    limit = int(request.args.get("limit", 20))
    with db_conn() as conn:
        rows = conn.execute("""
            SELECT
                ls.track_id, ls.liked_at, ls.review_status, ls.review_notes,
                t.name, t.primary_artist_name, t.artist_names,
                t.duration_ms, t.popularity, t.preview_url, t.spotify_url, t.explicit,
                al.name AS album_name, al.release_date, al.image_url AS album_image, al.album_type,
                af.energy, af.valence, af.tempo, af.danceability, af.acousticness,
                af.instrumentalness, af.speechiness,
                ph.play_count, ph.total_minutes, ph.skip_rate_pct,
                ph.last_played_at, ph.days_since_played
            FROM liked_songs ls
            JOIN tracks t ON ls.track_id = t.id
            LEFT JOIN albums al ON t.album_id = al.id
            LEFT JOIN audio_features af ON ls.track_id = af.track_id
            LEFT JOIN (
                SELECT
                    track_id,
                    COUNT(*) as play_count,
                    ROUND(SUM(ms_played) / 60000.0, 1) as total_minutes,
                    ROUND(AVG(skipped) * 100, 1) as skip_rate_pct,
                    MAX(played_at) as last_played_at,
                    CAST((julianday('now') - julianday(MAX(played_at))) AS INTEGER) as days_since_played
                FROM play_history
                WHERE source = 'spotify_export'
                GROUP BY track_id
            ) ph ON ph.track_id = ls.track_id
            WHERE ls.review_status = 'unreviewed'
            ORDER BY ls.liked_at ASC
            LIMIT ?
        """, (limit,)).fetchall()
        total_unreviewed = conn.execute("SELECT COUNT(*) as n FROM liked_songs WHERE review_status = 'unreviewed'").fetchone()["n"]
        total_reviewed = conn.execute("SELECT COUNT(*) as n FROM liked_songs WHERE review_status != 'unreviewed'").fetchone()["n"]
        total = conn.execute("SELECT COUNT(*) as n FROM liked_songs").fetchone()["n"]
    return jsonify({
        "tracks": [dict(r) for r in rows],
        "queue_stats": {
            "total": total,
            "unreviewed": total_unreviewed,
            "reviewed": total_reviewed,
            "progress_pct": round((total_reviewed / total * 100) if total > 0 else 0, 1),
        }
    })


@app.route("/api/review/decision", methods=["POST"])
def review_decision():
    data = request.json
    if not data or not data.get("track_id") or not data.get("status"):
        return jsonify({"error": "track_id and status required"}), 400
    valid_statuses = {"love", "keep", "archive_candidate", "skip", "unreviewed", "archived", "deleted"}
    if data["status"] not in valid_statuses:
        return jsonify({"error": f"Invalid status"}), 400
    with db_conn() as conn:
        conn.execute("""
            UPDATE liked_songs SET
                review_status = ?, review_notes = ?,
                reviewed_at = datetime('now'), updated_at = datetime('now')
            WHERE track_id = ?
        """, (data["status"], data.get("notes"), data["track_id"]))
    return jsonify({"ok": True, "track_id": data["track_id"], "status": data["status"]})


@app.route("/api/review/undo", methods=["POST"])
def review_undo():
    with db_conn() as conn:
        row = conn.execute("""
            SELECT track_id FROM liked_songs
            WHERE review_status != 'unreviewed'
            ORDER BY reviewed_at DESC LIMIT 1
        """).fetchone()
        if not row:
            return jsonify({"error": "Nothing to undo"}), 404
        conn.execute("""
            UPDATE liked_songs SET
                review_status = 'unreviewed', reviewed_at = NULL, updated_at = datetime('now')
            WHERE track_id = ?
        """, (row["track_id"],))
    return jsonify({"ok": True, "track_id": row["track_id"]})


@app.route("/api/review/stats")
def review_stats():
    with db_conn() as conn:
        rows = conn.execute("SELECT review_status, COUNT(*) as n FROM liked_songs GROUP BY review_status").fetchall()
        total = conn.execute("SELECT COUNT(*) as n FROM liked_songs").fetchone()["n"]
    breakdown = {row["review_status"]: row["n"] for row in rows}
    reviewed = total - breakdown.get("unreviewed", total)
    return jsonify({
        "total": total, "reviewed": reviewed,
        "unreviewed": breakdown.get("unreviewed", 0),
        "progress_pct": round((reviewed / total * 100) if total > 0 else 0, 1),
        "breakdown": breakdown,
    })


@app.route("/api/dashboard/listening")
def dashboard_listening():
    """Real listening-behaviour analytics from play_history (Extended
    Streaming History export). Distinct from dashboard_overview, which is
    based on when songs were liked, not when/how they were actually played.
    """
    with db_conn() as conn:
        has_history = conn.execute(
            "SELECT COUNT(*) as n FROM play_history WHERE source = 'spotify_export'"
        ).fetchone()["n"]

        if has_history == 0:
            return jsonify({"available": False})

        # Plays per year (actual listening activity, not like-dates)
        plays_by_year = conn.execute("""
            SELECT substr(played_at, 1, 4) as year, COUNT(*) as plays,
                   SUM(CASE WHEN ms_played > 30000 THEN 1 ELSE 0 END) as real_plays
            FROM play_history WHERE source = 'spotify_export'
            GROUP BY year ORDER BY year
        """).fetchall()

        # Top tracks by actual listening time (not just liked-song count)
        top_by_time = conn.execute("""
            SELECT t.name, t.primary_artist_name as artist,
                   COUNT(*) as play_count,
                   ROUND(SUM(ph.ms_played) / 60000.0, 1) as total_minutes,
                   ROUND(AVG(ph.skipped) * 100, 1) as skip_rate_pct
            FROM play_history ph
            JOIN tracks t ON t.id = ph.track_id
            WHERE ph.source = 'spotify_export'
            GROUP BY ph.track_id
            ORDER BY total_minutes DESC
            LIMIT 15
        """).fetchall()

        # Forgotten favourites: liked, decent play history, but not played
        # in a long time -- the brief's "forgotten gems" concept made concrete
        forgotten = conn.execute("""
            SELECT t.name, t.primary_artist_name as artist,
                   COUNT(*) as play_count,
                   MAX(ph.played_at) as last_played_at,
                   CAST((julianday('now') - julianday(MAX(ph.played_at))) AS INTEGER) as days_since_played
            FROM play_history ph
            JOIN tracks t ON t.id = ph.track_id
            JOIN liked_songs ls ON ls.track_id = t.id
            WHERE ph.source = 'spotify_export'
            GROUP BY ph.track_id
            HAVING play_count >= 5 AND days_since_played > 365
            ORDER BY play_count DESC, days_since_played DESC
            LIMIT 15
        """).fetchall()

        # Skip rate distribution -- which tracks you consistently skip
        # (candidates for archiving, per the project's evidence-based principle)
        high_skip = conn.execute("""
            SELECT t.name, t.primary_artist_name as artist,
                   COUNT(*) as total_plays,
                   ROUND(AVG(ph.skipped) * 100, 1) as skip_rate_pct
            FROM play_history ph
            JOIN tracks t ON t.id = ph.track_id
            JOIN liked_songs ls ON ls.track_id = t.id
            WHERE ph.source = 'spotify_export'
            GROUP BY ph.track_id
            HAVING total_plays >= 5 AND skip_rate_pct >= 50
            ORDER BY skip_rate_pct DESC, total_plays DESC
            LIMIT 15
        """).fetchall()

        # Overall skip rate + listening totals
        overview = conn.execute("""
            SELECT COUNT(*) as total_plays,
                   ROUND(AVG(skipped) * 100, 1) as overall_skip_rate_pct,
                   ROUND(SUM(ms_played) / 3600000.0, 1) as total_hours,
                   COUNT(DISTINCT track_id) as unique_tracks_played,
                   MIN(played_at) as earliest_play,
                   MAX(played_at) as latest_play
            FROM play_history WHERE source = 'spotify_export'
        """).fetchone()

        # Tracks discovered via history but never liked (streamed only)
        streamed_never_liked = conn.execute("""
            SELECT COUNT(DISTINCT ph.track_id) as n
            FROM play_history ph
            LEFT JOIN liked_songs ls ON ls.track_id = ph.track_id
            WHERE ph.source = 'spotify_export' AND ls.track_id IS NULL
        """).fetchone()["n"]

    return jsonify({
        "available": True,
        "overview": dict(overview),
        "streamed_never_liked": streamed_never_liked,
        "plays_by_year": [dict(r) for r in plays_by_year],
        "top_by_listening_time": [dict(r) for r in top_by_time],
        "forgotten_favourites": [dict(r) for r in forgotten],
        "high_skip_rate": [dict(r) for r in high_skip],
    })


@app.route("/api/import/enrich-tracks", methods=["POST"])
def trigger_track_enrichment():
    try:
        client = get_spotify_client()
        from backend.importers.track_enrichment import enrich_stub_tracks
        counts = enrich_stub_tracks(client)
        return jsonify({"status": "completed", "counts": counts})
    except Exception as e:
        return jsonify({"status": "failed", "error": str(e)}), 500


@app.route("/api/import/streaming-history", methods=["POST"])
def trigger_streaming_history_import():
    data = request.json or {}
    export_dir = data.get("export_dir")
    if not export_dir:
        return jsonify({"error": "export_dir required"}), 400
    try:
        from backend.importers.streaming_history_importer import import_streaming_history
        counts = import_streaming_history(export_dir)
        return jsonify({"status": "completed", "counts": counts})
    except Exception as e:
        return jsonify({"status": "failed", "error": str(e)}), 500


@app.route("/api/discovery/overview")
def discovery_overview():
    """
    Cross-references play_history against playlist_tracks and liked_songs to
    surface: tracks played heavily but never added to any playlist, tracks
    trending upward in the last 60 days vs the 60 days before that, and
    forgotten favourites. Each bucket returns track_ids so the frontend can
    turn any bucket directly into a real Spotify playlist.
    """
    with db_conn() as conn:
        has_history = conn.execute(
            "SELECT COUNT(*) as n FROM play_history WHERE source = 'spotify_export'"
        ).fetchone()["n"]
        if has_history == 0:
            return jsonify({"available": False})

        # Heavily played but never on any playlist -- "ready to playlist"
        unplaylisted = conn.execute("""
            SELECT ph.track_id, t.name, t.primary_artist_name as artist,
                   ph.play_count, ph.total_minutes
            FROM (
                SELECT track_id, COUNT(*) as play_count,
                       ROUND(SUM(ms_played) / 60000.0, 1) as total_minutes
                FROM play_history WHERE source = 'spotify_export'
                GROUP BY track_id
            ) ph
            JOIN tracks t ON t.id = ph.track_id
            LEFT JOIN playlist_tracks pt ON pt.track_id = ph.track_id
            WHERE pt.track_id IS NULL AND ph.play_count >= 10
            GROUP BY ph.track_id
            ORDER BY ph.play_count DESC
            LIMIT 25
        """).fetchall()

        # Trending up: plays in the last 60 days vs the 60 days before that
        trending_tracks = conn.execute("""
            WITH recent AS (
                SELECT track_id, COUNT(*) as recent_plays
                FROM play_history
                WHERE source = 'spotify_export' AND played_at >= datetime('now', '-60 days')
                GROUP BY track_id
            ),
            prior AS (
                SELECT track_id, COUNT(*) as prior_plays
                FROM play_history
                WHERE source = 'spotify_export'
                  AND played_at >= datetime('now', '-120 days')
                  AND played_at <  datetime('now', '-60 days')
                GROUP BY track_id
            )
            SELECT r.track_id, t.name, t.primary_artist_name as artist,
                   r.recent_plays, COALESCE(p.prior_plays, 0) as prior_plays,
                   (r.recent_plays - COALESCE(p.prior_plays, 0)) as delta
            FROM recent r
            JOIN tracks t ON t.id = r.track_id
            LEFT JOIN prior p ON p.track_id = r.track_id
            WHERE r.recent_plays >= 5 AND delta > 0
            ORDER BY delta DESC
            LIMIT 25
        """).fetchall()

        # Same idea at artist level -- rising artists, not just individual tracks
        trending_artists = conn.execute("""
            WITH recent AS (
                SELECT t.primary_artist_name as artist, COUNT(*) as recent_plays
                FROM play_history ph JOIN tracks t ON t.id = ph.track_id
                WHERE ph.source = 'spotify_export' AND ph.played_at >= datetime('now', '-60 days')
                  AND t.primary_artist_name IS NOT NULL
                GROUP BY t.primary_artist_name
            ),
            prior AS (
                SELECT t.primary_artist_name as artist, COUNT(*) as prior_plays
                FROM play_history ph JOIN tracks t ON t.id = ph.track_id
                WHERE ph.source = 'spotify_export'
                  AND ph.played_at >= datetime('now', '-120 days')
                  AND ph.played_at <  datetime('now', '-60 days')
                  AND t.primary_artist_name IS NOT NULL
                GROUP BY t.primary_artist_name
            )
            SELECT r.artist, r.recent_plays, COALESCE(p.prior_plays, 0) as prior_plays,
                   (r.recent_plays - COALESCE(p.prior_plays, 0)) as delta
            FROM recent r
            LEFT JOIN prior p ON p.artist = r.artist
            WHERE r.recent_plays >= 5 AND delta > 0
            ORDER BY delta DESC
            LIMIT 15
        """).fetchall()

        # Forgotten favourites, same definition as the listening dashboard,
        # but including track_id here so it can seed a playlist
        forgotten = conn.execute("""
            SELECT ph.track_id, t.name, t.primary_artist_name as artist,
                   COUNT(*) as play_count,
                   MAX(ph.played_at) as last_played_at,
                   CAST((julianday('now') - julianday(MAX(ph.played_at))) AS INTEGER) as days_since_played
            FROM play_history ph
            JOIN tracks t ON t.id = ph.track_id
            JOIN liked_songs ls ON ls.track_id = t.id
            WHERE ph.source = 'spotify_export'
            GROUP BY ph.track_id
            HAVING play_count >= 5 AND days_since_played > 180
            ORDER BY play_count DESC
            LIMIT 25
        """).fetchall()

    return jsonify({
        "available": True,
        "unplaylisted_high_plays": [dict(r) for r in unplaylisted],
        "trending_tracks": [dict(r) for r in trending_tracks],
        "trending_artists": [dict(r) for r in trending_artists],
        "forgotten_favourites": [dict(r) for r in forgotten],
    })


@app.route("/api/playlists/create", methods=["POST"])
def create_playlist():
    """
    Creates a real playlist on Spotify from a list of track_ids, then mirrors
    it into the local playlists/playlist_tracks tables so it shows up
    immediately in future imports/dashboards without waiting on the next
    import-playlists run.
    """
    data = request.json or {}
    name = data.get("name")
    track_ids = data.get("track_ids") or []
    description = data.get("description", "Created by Music Intelligence")

    if not name or not track_ids:
        return jsonify({"error": "name and track_ids are required"}), 400

    try:
        client = get_spotify_client()
        user_id = client.me()["id"]
        playlist = client.user_playlist_create(
            user_id, name, public=False, description=description
        )

        # Spotify caps playlist_add_items at 100 URIs per call
        uris = [f"spotify:track:{tid}" for tid in track_ids]
        for i in range(0, len(uris), 100):
            client.playlist_add_items(playlist["id"], uris[i:i + 100])

        from backend.importers.playlists import _upsert_playlist, _upsert_playlist_track
        with db_conn() as conn:
            _upsert_playlist(conn, playlist)
            for position, track_id in enumerate(track_ids):
                _upsert_playlist_track(conn, playlist["id"], track_id, None, user_id, position)

        return jsonify({
            "ok": True,
            "playlist_id": playlist["id"],
            "spotify_url": playlist.get("external_urls", {}).get("spotify"),
            "track_count": len(track_ids),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/import/playlists", methods=["POST"])
def trigger_playlist_import():
    try:
        client = get_spotify_client()
        from backend.importers.playlists import import_playlists
        counts = import_playlists(client)
        return jsonify({"status": "completed", "counts": counts})
    except Exception as e:
        return jsonify({"status": "failed", "error": str(e)}), 500


def run():
    init_db()
    logger.info("Starting Music Intelligence API on port %d", config.FLASK_PORT)
    app.run(host="0.0.0.0", port=config.FLASK_PORT, debug=True, use_reloader=False)


# ---------------------------------------------------------------------------
# Dashboard Analytics
# ---------------------------------------------------------------------------

@app.route("/api/dashboard/overview")
def dashboard_overview():
    """All data needed for the dashboard in one call."""
    import json
    from collections import Counter

    with db_conn() as conn:
        # Songs added per year
        yearly = conn.execute("""
            SELECT substr(liked_at, 1, 4) as year, COUNT(*) as n
            FROM liked_songs
            WHERE liked_at IS NOT NULL
            GROUP BY year ORDER BY year
        """).fetchall()

        # Top genres from artist data
        genre_rows = conn.execute("""
            SELECT a.genres FROM artists a
            JOIN tracks t ON t.primary_artist_id = a.id
            JOIN liked_songs ls ON ls.track_id = t.id
            WHERE a.genres IS NOT NULL AND a.genres != '[]'
        """).fetchall()

        genre_counts = Counter()
        for r in genre_rows:
            try:
                for g in json.loads(r["genres"]):
                    genre_counts[g] += 1
            except Exception:
                pass
        top_genres = [{"genre": g, "count": c} for g, c in genre_counts.most_common(12)]

        # Audio feature averages
        features = conn.execute("""
            SELECT
                AVG(energy) as energy, AVG(valence) as valence,
                AVG(danceability) as danceability, AVG(tempo) as tempo,
                AVG(acousticness) as acousticness,
                AVG(instrumentalness) as instrumentalness
            FROM audio_features af
            JOIN liked_songs ls ON ls.track_id = af.track_id
        """).fetchone()

        # Review status breakdown
        review_rows = conn.execute("""
            SELECT review_status, COUNT(*) as n
            FROM liked_songs GROUP BY review_status
        """).fetchall()

        # Decade breakdown
        decade_rows = conn.execute("""
            SELECT substr(al.release_date, 1, 3) || '0s' as decade, COUNT(*) as n
            FROM liked_songs ls
            JOIN tracks t ON ls.track_id = t.id
            JOIN albums al ON t.album_id = al.id
            WHERE al.release_date IS NOT NULL AND al.release_date != ''
            GROUP BY decade ORDER BY decade
        """).fetchall()

        # Top artists by liked song count
        top_artists = conn.execute("""
            SELECT t.primary_artist_name as artist, COUNT(*) as n
            FROM liked_songs ls
            JOIN tracks t ON ls.track_id = t.id
            WHERE t.primary_artist_name IS NOT NULL
            GROUP BY t.primary_artist_name
            ORDER BY n DESC LIMIT 15
        """).fetchall()

        # Energy distribution buckets
        energy_dist = conn.execute("""
            SELECT
                CASE
                    WHEN energy < 0.2 THEN 'Very Low'
                    WHEN energy < 0.4 THEN 'Low'
                    WHEN energy < 0.6 THEN 'Medium'
                    WHEN energy < 0.8 THEN 'High'
                    ELSE 'Very High'
                END as bucket,
                COUNT(*) as n
            FROM audio_features af
            JOIN liked_songs ls ON ls.track_id = af.track_id
            GROUP BY bucket
        """).fetchall()

        # Total counts
        total = conn.execute("SELECT COUNT(*) as n FROM liked_songs").fetchone()["n"]
        total_artists = conn.execute("SELECT COUNT(*) as n FROM artists").fetchone()["n"]
        total_albums = conn.execute("SELECT COUNT(*) as n FROM albums").fetchone()["n"]
        with_features = conn.execute("SELECT COUNT(*) as n FROM audio_features").fetchone()["n"]
        reviewed = conn.execute("SELECT COUNT(*) as n FROM liked_songs WHERE review_status != 'unreviewed'").fetchone()["n"]

    return jsonify({
        "totals": {
            "liked_songs": total,
            "artists": total_artists,
            "albums": total_albums,
            "with_features": with_features,
            "reviewed": reviewed,
            "review_pct": round(reviewed / total * 100, 1) if total > 0 else 0,
        },
        "yearly_growth": [dict(r) for r in yearly],
        "top_genres": top_genres,
        "audio_features": dict(features) if features else {},
        "review_breakdown": {r["review_status"]: r["n"] for r in review_rows},
        "decade_breakdown": [dict(r) for r in decade_rows],
        "top_artists": [dict(r) for r in top_artists],
        "energy_distribution": [dict(r) for r in energy_dist],
    })


@app.route("/api/import/artists", methods=["POST"])
def trigger_artist_import():
    try:
        client = get_spotify_client()
        from backend.importers.artists import import_artist_genres
        counts = import_artist_genres(client)
        return jsonify({"status": "completed", "counts": counts})
    except Exception as e:
        return jsonify({"status": "failed", "error": str(e)}), 500
