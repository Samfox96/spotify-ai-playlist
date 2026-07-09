"""
Spotify OAuth 2.0 authentication.

Uses Spotipy's CacheFileHandler to persist tokens locally in data/.spotify_cache
so the user doesn't re-auth on every run.

Flow:
1. First run → opens browser to Spotify login
2. User approves → Spotify redirects to localhost:8888/callback
3. Token stored locally
4. Subsequent runs → token refreshed automatically
"""

import logging
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from spotipy.cache_handler import CacheFileHandler

from backend.config import config

logger = logging.getLogger(__name__)


def _build_auth_manager() -> SpotifyOAuth:
    """Construct the OAuth manager with local token cache."""
    cache_handler = CacheFileHandler(cache_path=str(config.SPOTIFY_CACHE_PATH))

    return SpotifyOAuth(
        client_id=config.SPOTIFY_CLIENT_ID,
        client_secret=config.SPOTIFY_CLIENT_SECRET,
        redirect_uri=config.SPOTIFY_REDIRECT_URI,
        scope=config.SPOTIFY_SCOPES,
        cache_handler=cache_handler,
        open_browser=True,          # Auto-opens browser on first auth
        show_dialog=False,          # Don't re-ask if already authorised
    )


def get_spotify_client() -> spotipy.Spotify:
    """
    Return an authenticated Spotipy client.

    On first call: opens browser → user logs in → token cached locally.
    On subsequent calls: loads cached token, refreshes if expired.

    Raises:
        ValueError: If required config keys are missing.
        spotipy.SpotifyException: If auth fails.
    """
    missing = config.validate()
    if missing:
        raise ValueError(
            f"Missing required config: {', '.join(missing)}\n"
            f"Copy .env.example to .env and fill in your Spotify credentials."
        )

    auth_manager = _build_auth_manager()

    # This triggers the browser flow on first run
    client = spotipy.Spotify(auth_manager=auth_manager)

    # Verify the token works
    try:
        me = client.me()
        logger.info(
            "Authenticated as: %s (%s)",
            me.get("display_name", "Unknown"),
            me.get("id", "Unknown"),
        )
    except Exception as e:
        logger.error("Spotify auth verification failed: %s", e)
        raise

    return client


def get_current_user(client: spotipy.Spotify) -> dict:
    """Return basic profile info for the authenticated user."""
    me = client.me()
    return {
        "id": me.get("id"),
        "display_name": me.get("display_name"),
        "email": me.get("email"),
        "country": me.get("country"),
        "followers": me.get("followers", {}).get("total"),
        "image_url": (me.get("images") or [{}])[0].get("url"),
        "spotify_url": me.get("external_urls", {}).get("spotify"),
        "product": me.get("product"),  # free | premium
    }
