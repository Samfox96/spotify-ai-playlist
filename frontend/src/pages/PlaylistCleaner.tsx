import { useState, useEffect, useCallback, useRef } from 'react'
import {
  getLibraryScopes, getLibraryQueue, submitLibraryDecision, undoLibraryDecision,
  getLibraryShuffle, createPlaylist,
  type LibraryScope, type ScopedQueueTrack, type ShuffleTrack,
} from '../services/api'

interface Props {
  onStatsChange: () => void
}

function formatDuration(ms: number): string {
  const m = Math.floor(ms / 60000)
  const s = Math.floor((ms % 60000) / 1000)
  return `${m}:${s.toString().padStart(2, '0')}`
}

function formatLikedDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-AU', { year: 'numeric', month: 'short' })
}

function yearsAgo(iso: string): string {
  const years = (Date.now() - new Date(iso).getTime()) / (1000 * 60 * 60 * 24 * 365)
  if (years < 1) return 'Less than a year ago'
  if (years < 1.5) return '1 year ago'
  return `${Math.round(years)} years ago`
}

function FeatureBar({ label, value, color }: { label: string; value: number | null; color: string }) {
  if (value === null) return null
  return (
    <div className="feature-row">
      <span className="feature-label">{label}</span>
      <div className="feature-track">
        <div className="feature-fill" style={{ width: `${Math.round(value * 100)}%`, background: color }} />
      </div>
      <span className="feature-val">{Math.round(value * 100)}</span>
    </div>
  )
}

function EvidencePanel({ track }: { track: ScopedQueueTrack }) {
  if (track.play_count === null || track.play_count === undefined) {
    return (
      <div className="evidence-panel evidence-panel-empty">
        No listening history for this track yet.
      </div>
    )
  }
  const monthsAgo = track.days_since_played !== null ? Math.round(track.days_since_played / 30) : null
  const highSkip = (track.skip_rate_pct ?? 0) >= 50
  const stale = (track.days_since_played ?? 0) > 365

  return (
    <div className="evidence-panel">
      <div className="evidence-panel-title">Listening evidence</div>
      <div className="evidence-panel-grid">
        <div className="evidence-stat">
          <span className="evidence-stat-value">{track.play_count}</span>
          <span className="evidence-stat-label">plays</span>
        </div>
        <div className="evidence-stat">
          <span className="evidence-stat-value">{track.total_minutes?.toLocaleString() ?? '—'}</span>
          <span className="evidence-stat-label">minutes</span>
        </div>
        <div className="evidence-stat">
          <span className="evidence-stat-value" style={{ color: highSkip ? '#f87171' : undefined }}>
            {track.skip_rate_pct}%
          </span>
          <span className="evidence-stat-label">skip rate</span>
        </div>
        <div className="evidence-stat">
          <span className="evidence-stat-value" style={{ color: stale ? '#fbbf24' : undefined }}>
            {monthsAgo !== null ? `${monthsAgo}mo` : '—'}
          </span>
          <span className="evidence-stat-label">since last played</span>
        </div>
      </div>
      {(highSkip || stale) && (
        <div className="evidence-hint">
          {highSkip && stale
            ? 'Frequently skipped and not played in a while — possible archive candidate.'
            : highSkip
            ? 'Frequently skipped when it plays.'
            : "Hasn't been played in a while."}
        </div>
      )}
    </div>
  )
}

function SourceBadges({ track }: { track: ScopedQueueTrack }) {
  const playlists = track.playlist_names ? track.playlist_names.split(', ') : []
  if (!track.is_liked && playlists.length === 0) {
    return <div className="source-badges"><span className="source-badge source-badge-streamed">Streamed only — not liked or playlisted</span></div>
  }
  return (
    <div className="source-badges">
      {!!track.is_liked && <span className="source-badge source-badge-liked">❤ Liked</span>}
      {playlists.slice(0, 3).map(p => <span key={p} className="source-badge source-badge-playlist">{p}</span>)}
      {playlists.length > 3 && <span className="source-badge">+{playlists.length - 3} more</span>}
    </div>
  )
}

function ShuffleTool({ scope, scopeName }: { scope: string; scopeName: string }) {
  const [open, setOpen] = useState(false)
  const [tracks, setTracks] = useState<ShuffleTrack[] | null>(null)
  const [loading, setLoading] = useState(false)
  const [name, setName] = useState('')
  const [status, setStatus] = useState<'idle' | 'creating' | 'done' | 'error'>('idle')
  const [resultUrl, setResultUrl] = useState<string | null>(null)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  const runShuffle = async () => {
    setLoading(true)
    setStatus('idle')
    try {
      const data = await getLibraryShuffle(scope)
      setTracks(data.tracks)
      setName(`${scopeName} (True Shuffle)`)
    } finally {
      setLoading(false)
    }
  }

  const saveAsPlaylist = async () => {
    if (!tracks) return
    setStatus('creating')
    setErrorMsg(null)
    try {
      const result = await createPlaylist(name, tracks.map(t => t.track_id))
      setResultUrl(result.spotify_url)
      setStatus('done')
    } catch (e: any) {
      setErrorMsg(e.response?.data?.error || e.message)
      setStatus('error')
    }
  }

  if (!open) {
    return (
      <button className="btn btn-secondary shuffle-toggle" onClick={() => { setOpen(true); runShuffle() }}>
        🔀 True Shuffle
      </button>
    )
  }

  return (
    <div className="shuffle-panel">
      <div className="shuffle-panel-header">
        <span>🔀 True Shuffle — {scopeName}</span>
        <button className="shuffle-close" onClick={() => setOpen(false)}>✕</button>
      </div>
      <p className="bucket-desc">
        Uniform random order (unlike Spotify's own weighted shuffle). Save it as a real
        playlist and play it in order for genuinely random playback.
      </p>
      {loading ? (
        <div className="no-data">Shuffling…</div>
      ) : tracks && tracks.length > 0 ? (
        <>
          <div className="evidence-list">
            {tracks.slice(0, 8).map((t, i) => (
              <div key={t.track_id} className="evidence-row">
                <div className="evidence-main">
                  <span className="evidence-name">{i + 1}. {t.name}</span>
                  <span className="evidence-sub">{t.artist}</span>
                </div>
              </div>
            ))}
          </div>
          {tracks.length > 8 && <div className="bucket-more">+ {tracks.length - 8} more</div>}
          <div className="playlist-create-row">
            <input className="playlist-name-input" value={name} onChange={e => setName(e.target.value)}
              disabled={status === 'creating' || status === 'done'} />
            {status !== 'done' ? (
              <button className="btn btn-primary" onClick={saveAsPlaylist} disabled={status === 'creating'}>
                {status === 'creating' ? 'Creating…' : `Save as Playlist (${tracks.length})`}
              </button>
            ) : (
              <a className="btn btn-secondary" href={resultUrl ?? '#'} target="_blank" rel="noreferrer">✓ Open on Spotify</a>
            )}
          </div>
          {status === 'error' && <div className="playlist-create-error">{errorMsg}</div>}
        </>
      ) : (
        <div className="no-data">No tracks in this scope yet.</div>
      )}
    </div>
  )
}

const DECISIONS = [
  { status: 'love',              label: '❤️ Love',    key: '1', desc: 'All-time favourite',       color: '#f9a8d4' },
  { status: 'keep',              label: '✅ Keep',    key: '2', desc: 'Still in rotation',        color: '#34d399' },
  { status: 'archive_candidate', label: '📦 Archive', key: '3', desc: 'Not for regular rotation', color: '#fbbf24' },
  { status: 'skip',              label: '⏭️ Skip',    key: '4', desc: 'Decide later',             color: '#6b6b80' },
]

const SCOPE_STORAGE_KEY = 'mi_cleaner_scope'
const STORAGE_KEY = 'mi_queue_position'

function savePosition(trackId: string) { try { localStorage.setItem(STORAGE_KEY, trackId) } catch {} }
function loadPosition(): string | null { try { return localStorage.getItem(STORAGE_KEY) } catch { return null } }
function clearPosition() { try { localStorage.removeItem(STORAGE_KEY) } catch {} }
function saveScope(id: string) { try { localStorage.setItem(SCOPE_STORAGE_KEY, id) } catch {} }
function loadScope(): string { try { return localStorage.getItem(SCOPE_STORAGE_KEY) || 'all' } catch { return 'all' } }

export default function PlaylistCleaner({ onStatsChange }: Props) {
  const [scopes, setScopes] = useState<LibraryScope[]>([])
  const [scope, setScope] = useState(loadScope())
  const [queue, setQueue] = useState<ScopedQueueTrack[]>([])
  const [current, setCurrent] = useState(0)
  const [stats, setStats] = useState<{ total: number; unreviewed: number; reviewed: number; progress_pct: number } | null>(null)
  const [loading, setLoading] = useState(true)
  const [deciding, setDeciding] = useState(false)
  const [lastDecision, setLastDecision] = useState<{ track: ScopedQueueTrack; status: string } | null>(null)
  const [showUndo, setShowUndo] = useState(false)
  const [sessionCounts, setSessionCounts] = useState({ love: 0, keep: 0, archive_candidate: 0, skip: 0 })

  const audioRef = useRef<HTMLAudioElement | null>(null)
  const [isPlaying, setIsPlaying] = useState(false)
  const [audioProgress, setAudioProgress] = useState(0)
  const [audioError, setAudioError] = useState(false)
  const progressInterval = useRef<number | null>(null)

  useEffect(() => { getLibraryScopes().then(d => setScopes(d.scopes)).catch(() => {}) }, [])

  const stopAudio = useCallback(() => {
    if (audioRef.current) { audioRef.current.pause(); audioRef.current.currentTime = 0 }
    setIsPlaying(false); setAudioProgress(0); setAudioError(false)
    if (progressInterval.current) clearInterval(progressInterval.current)
  }, [])

  const togglePreview = useCallback(() => {
    const track = queue[current]
    if (!track?.preview_url) return
    if (isPlaying) { stopAudio(); return }
    stopAudio(); setAudioError(false)
    const audio = new Audio(track.preview_url)
    audioRef.current = audio
    audio.onplay = () => {
      setIsPlaying(true)
      progressInterval.current = window.setInterval(() => {
        if (audio.duration) setAudioProgress(audio.currentTime / audio.duration)
      }, 100)
    }
    audio.onended = () => { setIsPlaying(false); setAudioProgress(0); if (progressInterval.current) clearInterval(progressInterval.current) }
    audio.onerror = () => { setIsPlaying(false); setAudioError(true) }
    audio.play().catch(() => setAudioError(true))
  }, [queue, current, isPlaying, stopAudio])

  useEffect(() => { stopAudio() }, [current, stopAudio])
  useEffect(() => () => { stopAudio() }, [stopAudio])

  const loadQueue = useCallback(async (resumeId?: string | null) => {
    setLoading(true)
    try {
      const data = await getLibraryQueue(scope, 50)
      setQueue(data.tracks)
      setStats(data.queue_stats)
      const savedId = resumeId !== undefined ? resumeId : loadPosition()
      if (savedId && data.tracks.length > 0) {
        const idx = data.tracks.findIndex((t: ScopedQueueTrack) => t.track_id === savedId)
        setCurrent(idx >= 0 ? idx : 0)
      } else {
        setCurrent(0)
      }
    } catch (e) {
      console.error('Failed to load queue', e)
    } finally {
      setLoading(false)
    }
  }, [scope])

  useEffect(() => { loadQueue() }, [loadQueue])

  useEffect(() => { if (queue[current]) savePosition(queue[current].track_id) }, [current, queue])

  const changeScope = (id: string) => {
    clearPosition()
    setScope(id)
    saveScope(id)
  }

  const track = queue[current] ?? null

  const decide = useCallback(async (status: string) => {
    if (!track || deciding) return
    setDeciding(true)
    setLastDecision({ track, status })
    stopAudio()
    try {
      await submitLibraryDecision(track.track_id, status)
      setSessionCounts(prev => ({ ...prev, [status]: (prev as any)[status] + 1 }))
      onStatsChange()
      setShowUndo(true)
      setTimeout(() => setShowUndo(false), 5000)
      if (current + 1 < queue.length) {
        setCurrent(c => c + 1)
      } else {
        clearPosition()
        await loadQueue(null)
      }
    } catch (e) {
      console.error('Decision failed', e)
    } finally {
      setDeciding(false)
    }
  }, [track, deciding, current, queue.length, loadQueue, onStatsChange, stopAudio])

  const undo = useCallback(async () => {
    if (!lastDecision) return
    try {
      await undoLibraryDecision()
      setShowUndo(false)
      setQueue(prev => [lastDecision.track, ...prev.filter(t => t.track_id !== lastDecision.track.track_id)])
      setCurrent(0)
      setSessionCounts(prev => ({ ...prev, [lastDecision.status]: Math.max(0, (prev as any)[lastDecision.status] - 1) }))
      setLastDecision(null)
      onStatsChange()
    } catch (e) {
      console.error('Undo failed', e)
    }
  }, [lastDecision, onStatsChange])

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return
      const decision = DECISIONS.find(d => d.key === e.key)
      if (decision) decide(decision.status)
      if ((e.key === 'z' && (e.metaKey || e.ctrlKey))) undo()
      if (e.key === 'ArrowRight' && current + 1 < queue.length) setCurrent(c => c + 1)
      if (e.key === 'ArrowLeft' && current > 0) setCurrent(c => c - 1)
      if (e.key === ' ') { e.preventDefault(); togglePreview() }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [decide, undo, current, queue.length, togglePreview])

  const currentScope = scopes.find(s => s.id === scope)
  const scopeName = currentScope?.name ?? 'All Music'

  return (
    <div className="queue-page">
      <div className="cleaner-header">
        <select className="scope-select" value={scope} onChange={e => changeScope(e.target.value)}>
          {scopes.map(s => <option key={s.id} value={s.id}>{s.name} ({s.count.toLocaleString()})</option>)}
        </select>
        <ShuffleTool scope={scope} scopeName={scopeName} />
      </div>

      {loading ? (
        <div className="queue-loading"><div className="spinner" />Loading your queue...</div>
      ) : !track ? (
        <div className="queue-empty">
          <div className="queue-empty-icon">🎉</div>
          <h2>Queue complete!</h2>
          <p>Everything in "{scopeName}" has been reviewed.</p>
          <button className="btn btn-primary" onClick={() => loadQueue(null)}>Reload Queue</button>
        </div>
      ) : (
        <>
          <div className="queue-header">
            <div className="queue-progress-bar">
              <div className="queue-progress-fill" style={{ width: `${stats?.progress_pct ?? 0}%` }} />
            </div>
            <div className="queue-progress-text">
              <span>{stats?.reviewed.toLocaleString() ?? 0} reviewed</span>
              <span>{stats?.progress_pct ?? 0}%</span>
              <span>{stats?.unreviewed.toLocaleString() ?? 0} remaining</span>
            </div>
          </div>

          <div className="session-tally">
            {DECISIONS.map(d => (
              <div key={d.status} className="tally-item">
                <span className="tally-label">{d.label.split(' ')[0]}</span>
                <span className="tally-count" style={{ color: d.color }}>{(sessionCounts as any)[d.status]}</span>
              </div>
            ))}
          </div>

          <div className="track-card">
            <div className="track-card-inner">
              <div className="album-art-wrap">
                {track.album_image
                  ? <img src={track.album_image} alt={track.album_name ?? ''} className="album-art" />
                  : <div className="album-art-placeholder">♪</div>
                }
                <button
                  className={`preview-btn ${isPlaying ? 'playing' : ''} ${!track.preview_url ? 'no-preview' : ''}`}
                  onClick={togglePreview}
                  disabled={!track.preview_url}
                  title={!track.preview_url ? 'No preview available' : isPlaying ? 'Stop preview' : 'Play 30s preview (Space)'}
                >
                  {!track.preview_url ? <span className="preview-icon">🔇</span>
                    : isPlaying ? (<><span className="preview-icon">⏹</span><div className="preview-progress" style={{ width: `${audioProgress * 100}%` }} /></>)
                    : <span className="preview-icon">▶</span>}
                </button>
                {audioError && <div className="preview-error">Preview unavailable</div>}
              </div>

              <div className="track-info">
                <div className="track-name">{track.name}</div>
                <div className="track-artist">{track.primary_artist_name}</div>
                <div className="track-meta-row">
                  {track.album_name && <span className="track-album">{track.album_name}</span>}
                  {track.release_date && <span className="track-year">{track.release_date.slice(0, 4)}</span>}
                  {track.explicit === 1 && <span className="explicit-badge">E</span>}
                </div>

                <SourceBadges track={track} />

                {track.liked_at && (
                  <div className="liked-info">
                    <span className="liked-label">Liked</span>
                    <span className="liked-date">{formatLikedDate(track.liked_at)}</span>
                    <span className="liked-ago">— {yearsAgo(track.liked_at)}</span>
                  </div>
                )}

                {track.duration_ms && <div className="track-duration">{formatDuration(track.duration_ms)}</div>}

                <div className={`preview-hint ${!track.preview_url ? 'no-preview-hint' : ''}`}>
                  {track.preview_url ? (isPlaying ? '🎵 Playing preview...' : 'Press Space to preview') : '🔇 No preview available for this track'}
                </div>

                {(track.energy !== null || track.valence !== null) && (
                  <div className="features-section">
                    <FeatureBar label="Energy" value={track.energy} color="#f87171" />
                    <FeatureBar label="Mood" value={track.valence} color="#fbbf24" />
                    <FeatureBar label="Dance" value={track.danceability} color="#34d399" />
                    <FeatureBar label="Acoustic" value={track.acousticness} color="#7c5cbf" />
                  </div>
                )}
                {track.tempo && <div className="tempo-badge">{Math.round(track.tempo)} BPM</div>}

                <EvidencePanel track={track} />

                {track.spotify_url && (
                  <a href={track.spotify_url} target="_blank" rel="noreferrer" className="spotify-link">Open in Spotify ↗</a>
                )}
              </div>
            </div>

            <div className="decision-buttons">
              {DECISIONS.map(d => (
                <button key={d.status} className="decision-btn" style={{ '--btn-color': d.color } as any}
                  onClick={() => decide(d.status)} disabled={deciding} title={d.desc}>
                  <span className="decision-emoji">{d.label.split(' ')[0]}</span>
                  <span className="decision-text">{d.label.split(' ').slice(1).join(' ')}</span>
                  <span className="decision-key">{d.key}</span>
                </button>
              ))}
            </div>

            <div className="card-nav">
              <button className="nav-btn" onClick={() => setCurrent(c => Math.max(0, c - 1))} disabled={current === 0}>← Prev</button>
              <span className="card-position">{current + 1} / {queue.length}</span>
              <button className="nav-btn" onClick={() => setCurrent(c => Math.min(queue.length - 1, c + 1))} disabled={current === queue.length - 1}>Next →</button>
            </div>
          </div>

          {showUndo && lastDecision && (
            <div className="undo-toast">
              Marked as <strong>{lastDecision.status.replace('_', ' ')}</strong>
              <button className="undo-btn" onClick={undo}>↩ Undo</button>
            </div>
          )}

          <div className="keyboard-hint">
            Press <kbd>1</kbd> Love · <kbd>2</kbd> Keep · <kbd>3</kbd> Archive · <kbd>4</kbd> Skip · <kbd>Space</kbd> Preview · <kbd>←</kbd><kbd>→</kbd> Navigate · <kbd>Ctrl+Z</kbd> Undo
          </div>
        </>
      )}
    </div>
  )
}
