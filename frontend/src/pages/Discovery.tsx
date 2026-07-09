import { useState, useEffect } from 'react'
import {
  getDiscoveryOverview, createPlaylist, importPlaylists,
  type DiscoveryOverview, type DiscoveryTrack, type TrendingArtist,
} from '../services/api'

function TrackBucket({
  title, description, tracks, defaultName, metricLabel, metricFn,
}: {
  title: string
  description: string
  tracks: DiscoveryTrack[]
  defaultName: string
  metricLabel: string
  metricFn: (t: DiscoveryTrack) => string
}) {
  const [name, setName] = useState(defaultName)
  const [status, setStatus] = useState<'idle' | 'creating' | 'done' | 'error'>('idle')
  const [resultUrl, setResultUrl] = useState<string | null>(null)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  const handleCreate = async () => {
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

  if (tracks.length === 0) {
    return (
      <div className="dash-card">
        <h2 className="dash-card-title">{title}</h2>
        <div className="no-data">Nothing here right now -- {description.toLowerCase()}</div>
      </div>
    )
  }

  return (
    <div className="dash-card span-2">
      <h2 className="dash-card-title">{title} <span className="bucket-count">({tracks.length})</span></h2>
      <p className="bucket-desc">{description}</p>
      <div className="evidence-list">
        {tracks.slice(0, 10).map(t => (
          <div key={t.track_id} className="evidence-row">
            <div className="evidence-main">
              <span className="evidence-name">{t.name}</span>
              <span className="evidence-sub">{t.artist}</span>
            </div>
            <div className="evidence-stats">
              <span>{metricLabel}: {metricFn(t)}</span>
            </div>
          </div>
        ))}
        {tracks.length > 10 && <div className="bucket-more">+ {tracks.length - 10} more</div>}
      </div>

      <div className="playlist-create-row">
        <input
          className="playlist-name-input"
          value={name}
          onChange={e => setName(e.target.value)}
          disabled={status === 'creating' || status === 'done'}
        />
        {status !== 'done' ? (
          <button
            className="btn btn-primary"
            onClick={handleCreate}
            disabled={status === 'creating'}
          >
            {status === 'creating' ? 'Creating…' : `Create playlist (${tracks.length} tracks)`}
          </button>
        ) : (
          <a className="btn btn-secondary" href={resultUrl ?? '#'} target="_blank" rel="noreferrer">
            ✓ Open on Spotify
          </a>
        )}
      </div>
      {status === 'error' && <div className="playlist-create-error">{errorMsg}</div>}
    </div>
  )
}

function ArtistBucket({ artists }: { artists: TrendingArtist[] }) {
  if (artists.length === 0) {
    return (
      <div className="dash-card">
        <h2 className="dash-card-title">Rising Artists</h2>
        <div className="no-data">No artists trending up right now</div>
      </div>
    )
  }
  return (
    <div className="dash-card">
      <h2 className="dash-card-title">Rising Artists</h2>
      <div className="evidence-list">
        {artists.map((a, i) => (
          <div key={i} className="evidence-row">
            <div className="evidence-main">
              <span className="evidence-name">{a.artist}</span>
            </div>
            <div className="evidence-stats">
              <span style={{ color: '#34d399' }}>+{a.delta} plays</span>
              <span>{a.recent_plays} recent vs {a.prior_plays} prior</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

export default function Discovery() {
  const [data, setData] = useState<DiscoveryOverview | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [importing, setImporting] = useState(false)
  const [importMsg, setImportMsg] = useState<string | null>(null)

  const load = () => {
    setLoading(true)
    getDiscoveryOverview()
      .then(setData)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  const handleImportPlaylists = async () => {
    setImporting(true)
    setImportMsg(null)
    try {
      const result = await importPlaylists()
      const c = result.counts
      setImportMsg(`Imported ${c.playlists} playlists, ${c.tracks_new_or_updated} tracks.`)
      load()
    } catch (e: any) {
      setImportMsg(`Error: ${e.response?.data?.error || e.message}`)
    } finally {
      setImporting(false)
    }
  }

  if (loading) return <div className="dash-loading"><div className="spinner" /> Loading discovery data...</div>
  if (error) return <div className="dash-error">Failed to load: {error}</div>
  if (!data) return null

  if (!data.available) {
    return (
      <div className="dashboard-page">
        <h1>Discovery</h1>
        <div className="no-data">
          Import your Spotify Extended Streaming History first (<code>import-history</code>) --
          discovery and trends are built from real listening data.
        </div>
      </div>
    )
  }

  return (
    <div className="dashboard-page">
      <div className="discovery-header">
        <h1>Discovery</h1>
        <button className="btn btn-secondary" onClick={handleImportPlaylists} disabled={importing}>
          {importing ? 'Syncing playlists…' : '🔄 Sync playlists from Spotify'}
        </button>
      </div>
      {importMsg && <div className="import-msg">{importMsg}</div>}

      <div className="dash-grid">
        <TrackBucket
          title="Ready to Playlist"
          description="Played heavily but never added to any playlist -- hidden gems in your own history."
          tracks={data.unplaylisted_high_plays ?? []}
          defaultName="Ready to Playlist"
          metricLabel="plays"
          metricFn={t => `${t.play_count} plays, ${t.total_minutes}min`}
        />

        <TrackBucket
          title="Rising Right Now"
          description="Tracks you've been playing a lot more in the last 60 days than the 60 days before."
          tracks={data.trending_tracks ?? []}
          defaultName="Rising Right Now"
          metricLabel="growth"
          metricFn={t => `+${t.delta} plays (${t.recent_plays} vs ${t.prior_plays})`}
        />

        <ArtistBucket artists={data.trending_artists ?? []} />

        <TrackBucket
          title="Forgotten Favourites"
          description="Liked and played heavily once, but you haven't touched them in 6+ months."
          tracks={data.forgotten_favourites ?? []}
          defaultName="Forgotten Favourites"
          metricLabel="last played"
          metricFn={t => `${Math.round((t.days_since_played ?? 0) / 30)} months ago`}
        />
      </div>
    </div>
  )
}
