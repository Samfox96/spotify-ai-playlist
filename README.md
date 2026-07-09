# Music Intelligence

A personal music operating system layered above Spotify.

> **Current phase:** Phase 1 — Foundation (Auth + Import + Local DB)

---

## Setup (Windows)

### Prerequisites

- Python 3.10+
- Node.js 18+
- A [Spotify Developer app](https://developer.spotify.com/dashboard) with:
  - Redirect URI set to: `http://localhost:8888/callback`

---

### 1. Clone and configure

```bash
git clone <your-repo>
cd music-intelligence

# Copy and fill in your credentials
copy .env.example .env
```

Edit `.env`:
```
SPOTIFY_CLIENT_ID=your_client_id
SPOTIFY_CLIENT_SECRET=your_client_secret
SPOTIFY_REDIRECT_URI=http://localhost:8888/callback
FLASK_SECRET_KEY=any-random-string
```

---

### 2. Backend

```bash
# Create virtual environment (recommended)
python -m venv .venv
.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

---

### 3. First run — authenticate with Spotify

```bash
python -m backend.cli import-liked
```

This will:
1. Open your browser → Spotify login
2. You approve the permissions
3. Token saved to `data/.spotify_cache`
4. Import begins

Subsequent runs skip the browser step.

---

### 4. Import audio features (after liked songs)

```bash
python -m backend.cli import-features
```

---

### 5. Check your stats

```bash
python -m backend.cli stats
```

---

### 6. Start the API server

```bash
python -m backend.cli serve
```

Server runs on `http://localhost:8888`

---

### 7. Start the frontend (separate terminal)

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`

---

## CLI Reference

```
python -m backend.cli import-liked          # Incremental sync
python -m backend.cli import-liked --full   # Full re-import
python -m backend.cli import-features       # Audio features
python -m backend.cli stats                 # DB stats
python -m backend.cli serve                 # API server
```

---

## Architecture

```
music-intelligence/
├── backend/
│   ├── auth/           # Spotify OAuth
│   ├── db/             # SQLite schema + connection
│   ├── importers/      # liked_songs, audio_features
│   ├── analysis/       # (Phase 3) Genre, mood, clustering
│   ├── api/            # Flask REST API
│   └── cli.py          # Command line interface
├── frontend/
│   └── src/
│       ├── services/   # API client
│       ├── components/ # (Phase 3) UI components
│       └── pages/      # Dashboard, Library, Review Queue
├── data/               # Local SQLite DB + token cache (gitignored)
├── docs/               # Architecture docs
└── .env                # Your credentials (gitignored)
```

---

## Data Philosophy

- **Local first.** All intelligence stored in `data/music_intelligence.db`
- **Non-destructive.** Review statuses: `unreviewed → keep → archive_candidate → archived → deleted`
- **No assumptions.** Missing data (play counts, features) stored as NULL
- **Modular.** Spotify is a source, not a dependency

---

## Roadmap

| Phase | Focus | Status |
|-------|-------|--------|
| 1 | Auth + Import + Local DB | ✅ Done |
| 2 | Spotify export, Last.fm, canonical data model | 🔜 Next |
| 3 | Dashboard, Review Queue, Library Intelligence | ⏳ |
| 4 | Discovery, Semantic search, Smart shuffle | ⏳ |
| 5 | Taste model, AI recommendations | ⏳ |

---

## Ideas Backlog

See `docs/PROJECT_IDEAS.md` for future concepts outside current scope.
