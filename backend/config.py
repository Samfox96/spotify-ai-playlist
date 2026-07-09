import os
from pathlib import Path
from dotenv import load_dotenv

_root = Path(__file__).parent.parent
load_dotenv(_root / ".env")

class Config:
    SPOTIFY_CLIENT_ID: str = os.getenv("SPOTIFY_CLIENT_ID", "")
    SPOTIFY_CLIENT_SECRET: str = os.getenv("SPOTIFY_CLIENT_SECRET", "")
    SPOTIFY_REDIRECT_URI: str = os.getenv("SPOTIFY_REDIRECT_URI", "http://localhost:8888/callback")
    SPOTIFY_SCOPES: str = " ".join([
        "user-library-read",
        "playlist-read-private",
        "playlist-read-collaborative",
        "playlist-modify-private",
        "playlist-modify-public",
        "user-read-recently-played",
        "user-top-read",
        "user-read-playback-state",
        "user-read-currently-playing",
    ])
    FLASK_SECRET_KEY: str = os.getenv("FLASK_SECRET_KEY", "dev-secret-change-me")
    FLASK_PORT: int = int(os.getenv("FLASK_PORT", "8888"))
    DB_PATH: Path = Path(os.getenv("DB_PATH", str(_root / "data" / "music_intelligence.db")))
    SPOTIFY_CACHE_PATH: Path = _root / "data" / ".spotify_cache"

    @classmethod
    def validate(cls) -> list:
        missing = []
        if not cls.SPOTIFY_CLIENT_ID:
            missing.append("SPOTIFY_CLIENT_ID")
        if not cls.SPOTIFY_CLIENT_SECRET:
            missing.append("SPOTIFY_CLIENT_SECRET")
        return missing

config = Config()