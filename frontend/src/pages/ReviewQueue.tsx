import { useState, useEffect, useCallback, useRef } from 'react'
import { getReviewQueue, submitDecision, undoLastDecision, type QueueTrack, type QueueStats } from '../services/api'

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

const DECISIONS = [
  { status: 'love',              label: '❤️ Love',    key: '1', desc: 'All-time favourite',       color: '#f9a8d4' },
  { status: 'keep',              label: '✅ Keep',    key: '2', desc: 'Still in rotation',        color: '#34d399' },
  { status: 'archive_candidate', label: '📦 Archive', key: '3', desc: 'Not for regular rotation', color: '#fbbf24' },
  { status: 'skip',              label: '⏭️ Skip',    key: '4', desc: 'Decide later',             color: '#6b6b80' },
]

const STORAGE_KEY = 'mi_queue_position'

function savePosition(trackId: string) {
  try { localStorage.setItem(STORAGE_KEY, trackId) } catch {}
}
function loadPosition(): string | null {
  try { return localStorage.getItem(STORAGE_KEY) } catch { return null }
}
function clearPosition() {
  try { localStorage.removeItem(STORAGE_KEY) } catch {}
}

export default function ReviewQueue({ onStatsChange }: Props) {
  const [queue, setQueue] = useState<QueueTrack[]>([])
  const [current, setCurrent] = useState(0)
  const [stats, setStats] = useState<QueueStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [deciding, setDeciding] = useState(false)
  const [lastDecision, setLastDecision] = useState<{ track: QueueTrack; status: string } | null>(null)
  const [showUndo, setShowUndo] = useState(false)
  const [sessionCounts, setSessionCounts] = useState({ love: 0, keep: 0, archive_candidate: 0, skip: 0 })

  // Audio preview state
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const [isPlaying, setIsPlaying] = useState(false)
  const [audioProgress, setAudioProgress] = useState(0)
  const [audioError, setAudioError] = useState(false)
  const progressInterval = useRef<number | null>(null)

  const stopAudio = useCallback(() => {
    if (audioRef.current) {
      audioRef.current.pause()
      audioRef.current.currentTime = 0
    }
    setIsPlaying(false)
    setAudioProgress(0)
    setAudioError(false)
    if (progressInterval.current) clearInterval(progressInterval.current)
  }, [])

  const togglePreview = useCallback(() => {
    const track = queue[current]
    if (!track?.preview_url) return

    if (isPlaying) {
      stopAudio()
      return
    }

    stopAudio()
    setAudioError(false)

    const audio = new Audio(track.preview_url)
    audioRef.current = audio

    audio.onplay = () => {
      setIsPlaying(true)
      progressInterval.current = window.setInterval(() => {
        if (audio.duration) {
          setAudioProgress(audio.currentTime / audio.duration)
        }
      }, 100)
    }
    audio.onended = () => {
      setIsPlaying(false)
      setAudioProgress(0)
      if (progressInterval.current) clearInterval(progressInterval.current)
    }
    audio.onerror = () => {
      setIsPlaying(false)
      setAudioError(true)
    }

    audio.play().catch(() => setAudioError(true))
  }, [queue, current, isPlaying, stopAudio])

  // Stop audio when track changes
  useEffect(() => { stopAudio() }, [current, stopAudio])

  // Cleanup on unmount
  useEffect(() => () => { stopAudio() }, [stopAudio])

  const loadQueue = useCallback(async (resumeId?: string | null) => {
    setLoading(true)
    try {
      const data = await getReviewQueue(50) // load 50 so resume works
      setQueue(data.tracks)
      setStats(data.queue_stats)

      // Resume position
      const savedId = resumeId !== undefined ? resumeId : loadPosition()
      if (savedId && data.tracks.length > 0) {
        const idx = data.tracks.findIndex((t: QueueTrack) => t.track_id === savedId)
        setCurrent(idx >= 0 ? idx : 0)
      } else {
        setCurrent(0)
      }
    } catch (e) {
      console.error('Failed to load queue', e)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadQueue() }, [loadQueue])

  // Save position whenever current changes
  useEffect(() => {
    if (queue[current]) savePosition(queue[current].track_id)
  }, [current, queue])

  const track = queue[current] ?? null

  const decide = useCallback(async (status: string) => {
    if (!track || deciding) return
    setDeciding(true)
    setLastDecision({ track, status })
    stopAudio()

    try {
      await submitDecision(track.track_id, status)
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
      await undoLastDecision()
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

  // Keyboard shortcuts
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

  if (loading) {
    return <div className="queue-loading"><div className="spinner" />Loading your queue...</div>
  }

  if (!track) {
    return (
      <div className="queue-empty">
        <div className="queue-empty-icon">🎉</div>
        <h2>Queue complete!</h2>
        <p>All tracks reviewed for now.</p>
        <button className="btn btn-primary" onClick={() => loadQueue(null)}>Reload Queue</button>
      </div>
    )
  }

  const progressPct = stats ? stats.progress_pct : 0
  const artists = (() => { try { return JSON.parse(track.artist_names).join(', ') } catch { return track.primary_artist_name } })()
  const hasPreview = !!track.preview_url

  return (
    <div className="queue-page">

      {/* Progress */}
      <div className="queue-header">
        <div className="queue-progress-bar">
          <div className="queue-progress-fill" style={{ width: `${progressPct}%` }} />
        </div>
        <div className="queue-progress-text">
          <span>{stats?.reviewed.toLocaleString() ?? 0} reviewed</span>
          <span>{progressPct}%</span>
          <span>{stats?.unreviewed.toLocaleString() ?? 0} remaining</span>
        </div>
      </div>

      {/* Session tally */}
      <div className="session-tally">
        {DECISIONS.map(d => (
          <div key={d.status} className="tally-item">
            <span className="tally-label">{d.label.split(' ')[0]}</span>
            <span className="tally-count" style={{ color: d.color }}>{(sessionCounts as any)[d.status]}</span>
          </div>
        ))}
      </div>

      {/* Track card */}
      <div className="track-card">
        <div className="track-card-inner">

          {/* Album art + preview button */}
          <div className="album-art-wrap">
            {track.album_image
              ? <img src={track.album_image} alt={track.album_name} className="album-art" />
              : <div className="album-art-placeholder">♪</div>
            }

            {/* Preview overlay */}
            <button
              className={`preview-btn ${isPlaying ? 'playing' : ''} ${!hasPreview ? 'no-preview' : ''}`}
              onClick={togglePreview}
              disabled={!hasPreview}
              title={!hasPreview ? 'No preview available' : isPlaying ? 'Stop preview' : 'Play 30s preview (Space)'}
            >
              {!hasPreview ? (
                <span className="preview-icon">🔇</span>
              ) : isPlaying ? (
                <>
                  <span className="preview-icon">⏹</span>
                  <div className="preview-progress" style={{ width: `${audioProgress * 100}%` }} />
                </>
              ) : (
                <span className="preview-icon">▶</span>
              )}
            </button>

            {audioError && <div className="preview-error">Preview unavailable</div>}
          </div>

          {/* Track info */}
          <div className="track-info">
            <div className="track-name">{track.name}</div>
            <div className="track-artist">{artists}</div>
            <div className="track-meta-row">
              <span className="track-album">{track.album_name}</span>
              {track.release_date && <span className="track-year">{track.release_date.slice(0, 4)}</span>}
              {track.explicit === 1 && <span className="explicit-badge">E</span>}
            </div>

            <div className="liked-info">
              <span className="liked-label">Liked</span>
              <span className="liked-date">{formatLikedDate(track.liked_at)}</span>
              <span className="liked-ago">— {yearsAgo(track.liked_at)}</span>
            </div>

            {track.duration_ms && <div className="track-duration">{formatDuration(track.duration_ms)}</div>}

            {/* Preview hint */}
            <div className={`preview-hint ${!hasPreview ? 'no-preview-hint' : ''}`}>
              {hasPreview
                ? isPlaying ? '🎵 Playing preview...' : 'Press Space to preview'
                : '🔇 No preview available for this track'}
            </div>

            {(track.energy !== null || track.valence !== null) && (
              <div className="features-section">
                <FeatureBar label="Energy"   value={track.energy}       color="#f87171" />
                <FeatureBar label="Mood"     value={track.valence}      color="#fbbf24" />
                <FeatureBar label="Dance"    value={track.danceability}  color="#34d399" />
                <FeatureBar label="Acoustic" value={track.acousticness}  color="#7c5cbf" />
              </div>
            )}
            {track.tempo && <div className="tempo-badge">{Math.round(track.tempo)} BPM</div>}

            {track.spotify_url && (
              <a href={track.spotify_url} target="_blank" rel="noreferrer" className="spotify-link">
                Open in Spotify ↗
              </a>
            )}
          </div>
        </div>

        {/* Decision buttons */}
        <div className="decision-buttons">
          {DECISIONS.map(d => (
            <button
              key={d.status}
              className="decision-btn"
              style={{ '--btn-color': d.color } as any}
              onClick={() => decide(d.status)}
              disabled={deciding}
              title={d.desc}
            >
              <span className="decision-emoji">{d.label.split(' ')[0]}</span>
              <span className="decision-text">{d.label.split(' ').slice(1).join(' ')}</span>
              <span className="decision-key">{d.key}</span>
            </button>
          ))}
        </div>

        {/* Navigation */}
        <div className="card-nav">
          <button className="nav-btn" onClick={() => setCurrent(c => Math.max(0, c - 1))} disabled={current === 0}>← Prev</button>
          <span className="card-position">{current + 1} / {queue.length}</span>
          <button className="nav-btn" onClick={() => setCurrent(c => Math.min(queue.length - 1, c + 1))} disabled={current === queue.length - 1}>Next →</button>
        </div>
      </div>

      {/* Undo toast */}
      {showUndo && lastDecision && (
        <div className="undo-toast">
          Marked as <strong>{lastDecision.status.replace('_', ' ')}</strong>
          <button className="undo-btn" onClick={undo}>↩ Undo</button>
        </div>
      )}

      <div className="keyboard-hint">
        Press <kbd>1</kbd> Love · <kbd>2</kbd> Keep · <kbd>3</kbd> Archive · <kbd>4</kbd> Skip · <kbd>Space</kbd> Preview · <kbd>←</kbd><kbd>→</kbd> Navigate · <kbd>Ctrl+Z</kbd> Undo
      </div>
    </div>
  )
}
