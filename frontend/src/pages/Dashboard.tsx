import { useState, useEffect } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  RadarChart, Radar, PolarGrid, PolarAngleAxis,
  PieChart, Pie, Cell, Legend
} from 'recharts'
import axios from 'axios'

interface DashboardData {
  totals: {
    liked_songs: number
    all_tracks: number
    artists: number
    albums: number
    with_features: number
    reviewed: number
    review_pct: number
  }
  yearly_growth: { year: string; n: number }[]
  top_genres: { genre: string; count: number }[]
  audio_features: {
    energy: number | null
    valence: number | null
    danceability: number | null
    tempo: number | null
    acousticness: number | null
    instrumentalness: number | null
  }
  review_breakdown: Record<string, number>
  decade_breakdown: { decade: string; n: number }[]
  top_artists: { artist: string; n: number }[]
  energy_distribution: { bucket: string; n: number }[]
  library_composition: { liked_only: number; playlist_only: number; streamed_only: number; overlapping: number }
}

interface HeatmapData {
  cells: { dow: number; hour: number; n: number }[]
}

interface HealthScoreData {
  available: boolean
  overall?: number
  components?: {
    review_progress: { score: number; detail: string }
    freshness: { score: number; detail: string }
    skip_health: { score: number; detail: string }
    diversity: { score: number; detail: string }
  }
}

interface MonthlyTrendData {
  months: { month: string; plays: number; hours: number }[]
}

interface SkipDistData {
  buckets: { bucket: string; n: number }[]
}

interface CompositionDetailTrack { track_id: string; name: string; artist: string }

interface ListeningData {
  available: boolean
  overview?: {
    total_plays: number
    overall_skip_rate_pct: number
    total_hours: number
    unique_tracks_played: number
    earliest_play: string
    latest_play: string
  }
  streamed_never_liked?: number
  plays_by_year?: { year: string; plays: number; real_plays: number }[]
  top_by_listening_time?: { name: string; artist: string; play_count: number; total_minutes: number; skip_rate_pct: number }[]
  forgotten_favourites?: { name: string; artist: string; play_count: number; last_played_at: string; days_since_played: number }[]
  high_skip_rate?: { name: string; artist: string; total_plays: number; skip_rate_pct: number }[]
}

const STATUS_COLORS: Record<string, string> = {
  love: '#f9a8d4',
  keep: '#34d399',
  archive_candidate: '#fbbf24',
  skip: '#6b6b80',
  unreviewed: '#2a2a35',
  archived: '#93c5fd',
  deleted: '#f87171',
}

const ENERGY_COLORS: Record<string, string> = {
  'Very Low': '#7c5cbf',
  'Low': '#818cf8',
  'Medium': '#34d399',
  'High': '#fbbf24',
  'Very High': '#f87171',
}

const ENERGY_ORDER = ['Very Low', 'Low', 'Medium', 'High', 'Very High']

function StatPill({ label, value, sub, accent }: { label: string; value: string | number; sub?: string; accent?: boolean }) {
  return (
    <div className={`stat-pill ${accent ? 'accent' : ''}`}>
      <div className="stat-pill-value">{typeof value === 'number' ? value.toLocaleString() : value}</div>
      <div className="stat-pill-label">{label}</div>
      {sub && <div className="stat-pill-sub">{sub}</div>}
    </div>
  )
}

function scoreColor(score: number): string {
  if (score >= 75) return '#34d399'
  if (score >= 50) return '#fbbf24'
  return '#f87171'
}

function HealthScoreCard({ data }: { data: HealthScoreData }) {
  if (!data.available || !data.overall || !data.components) {
    return <div className="no-data">Import listening history to unlock a health score</div>
  }
  const items = [
    { key: 'review_progress', label: 'Review Progress', ...data.components.review_progress },
    { key: 'freshness', label: 'Freshness', ...data.components.freshness },
    { key: 'skip_health', label: 'Skip Health', ...data.components.skip_health },
    { key: 'diversity', label: 'Diversity', ...data.components.diversity },
  ]
  return (
    <div className="health-score-wrap">
      <div className="health-score-main">
        <div className="health-score-circle" style={{ '--score-color': scoreColor(data.overall) } as any}>
          <span className="health-score-number">{Math.round(data.overall)}</span>
        </div>
        <div className="health-score-label">Overall Library Health</div>
      </div>
      <div className="health-score-components">
        {items.map(item => (
          <div key={item.key} className="health-component">
            <div className="health-component-header">
              <span>{item.label}</span>
              <span style={{ color: scoreColor(item.score) }}>{Math.round(item.score)}</span>
            </div>
            <div className="health-component-bar">
              <div className="health-component-fill" style={{ width: `${item.score}%`, background: scoreColor(item.score) }} />
            </div>
            <div className="health-component-detail">{item.detail}</div>
          </div>
        ))}
      </div>
    </div>
  )
}

function CompositionDrilldown({ bucket, label }: { bucket: string; label: string }) {
  const [tracks, setTracks] = useState<CompositionDetailTrack[] | null>(null)
  const [loading, setLoading] = useState(false)

  const load = () => {
    setLoading(true)
    axios.get('/api/dashboard/composition-detail', { params: { bucket } })
      .then(r => setTracks(r.data.tracks))
      .finally(() => setLoading(false))
  }

  return (
    <div className="composition-drilldown">
      {tracks === null ? (
        <button className="drilldown-toggle" onClick={load} disabled={loading}>
          {loading ? 'Loading…' : `Show tracks in "${label}"`}
        </button>
      ) : (
        <>
          <button className="drilldown-toggle" onClick={() => setTracks(null)}>Hide</button>
          <div className="evidence-list">
            {tracks.length > 0 ? tracks.map(t => (
              <div key={t.track_id} className="evidence-row">
                <div className="evidence-main">
                  <span className="evidence-name">{t.name}</span>
                  <span className="evidence-sub">{t.artist}</span>
                </div>
              </div>
            )) : <div className="no-data">Nothing in this bucket</div>}
          </div>
        </>
      )}
    </div>
  )
}

const DOW_LABELS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']

function HeatmapGrid({ cells }: { cells: { dow: number; hour: number; n: number }[] }) {
  const grid: number[][] = Array.from({ length: 7 }, () => Array(24).fill(0))
  let max = 1
  for (const c of cells) {
    grid[c.dow][c.hour] = c.n
    if (c.n > max) max = c.n
  }
  return (
    <div className="heatmap-wrap">
      <div className="heatmap-grid">
        {grid.map((row, dow) => (
          <div key={dow} className="heatmap-row">
            <span className="heatmap-dow-label">{DOW_LABELS[dow]}</span>
            {row.map((n, hour) => {
              const intensity = n / max
              return (
                <div
                  key={hour}
                  className="heatmap-cell"
                  style={{ background: intensity > 0 ? `rgba(124, 92, 191, ${0.12 + intensity * 0.88})` : 'var(--surface-2)' }}
                  title={`${DOW_LABELS[dow]} ${hour}:00 — ${n.toLocaleString()} plays`}
                />
              )
            })}
          </div>
        ))}
      </div>
      <div className="heatmap-hour-labels">
        {[0, 6, 12, 18].map(h => <span key={h} style={{ left: `${(h / 24) * 100}%` }}>{h}:00</span>)}
      </div>
    </div>
  )
}

function SectionCard({ title, children, className = '' }: { title: string; children: React.ReactNode; className?: string }) {
  return (
    <div className={`dash-card ${className}`}>
      <h2 className="dash-card-title">{title}</h2>
      {children}
    </div>
  )
}

function CustomTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null
  return (
    <div className="chart-tooltip">
      <div className="tooltip-label">{label}</div>
      {payload.map((p: any, i: number) => (
        <div key={i} style={{ color: p.color || 'var(--accent-2)' }}>
          {p.name}: {p.value?.toLocaleString?.() ?? p.value}
        </div>
      ))}
    </div>
  )
}

export default function Dashboard() {
  const [data, setData] = useState<DashboardData | null>(null)
  const [listening, setListening] = useState<ListeningData | null>(null)
  const [heatmap, setHeatmap] = useState<HeatmapData | null>(null)
  const [health, setHealth] = useState<HealthScoreData | null>(null)
  const [monthlyTrend, setMonthlyTrend] = useState<MonthlyTrendData | null>(null)
  const [skipDist, setSkipDist] = useState<SkipDistData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([
      axios.get('/api/dashboard/overview'),
      axios.get('/api/dashboard/listening'),
      axios.get('/api/dashboard/heatmap'),
      axios.get('/api/dashboard/health-score'),
      axios.get('/api/dashboard/monthly-trend'),
      axios.get('/api/dashboard/skip-distribution'),
    ])
      .then(([overviewRes, listeningRes, heatmapRes, healthRes, monthlyRes, skipRes]) => {
        setData(overviewRes.data)
        setListening(listeningRes.data)
        setHeatmap(heatmapRes.data)
        setHealth(healthRes.data)
        setMonthlyTrend(monthlyRes.data)
        setSkipDist(skipRes.data)
      })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="dash-loading"><div className="spinner" /> Loading dashboard...</div>
  if (error) return <div className="dash-error">Failed to load: {error}</div>
  if (!data) return null

  const { totals, yearly_growth, top_genres, audio_features, review_breakdown,
          decade_breakdown, top_artists, energy_distribution, library_composition } = data

  // Radar chart data for audio features
  const radarData = [
    { feature: 'Energy',      value: Math.round((audio_features.energy ?? 0) * 100) },
    { feature: 'Mood',        value: Math.round((audio_features.valence ?? 0) * 100) },
    { feature: 'Danceability',value: Math.round((audio_features.danceability ?? 0) * 100) },
    { feature: 'Acoustic',    value: Math.round((audio_features.acousticness ?? 0) * 100) },
    { feature: 'Instrumental',value: Math.round((audio_features.instrumentalness ?? 0) * 100) },
  ]

  // Pie data for review status
  const reviewPieData = Object.entries(review_breakdown)
    .filter(([, n]) => n > 0)
    .map(([status, n]) => ({ name: status.replace('_', ' '), value: n, status }))

  // Sort energy distribution
  const sortedEnergy = [...energy_distribution].sort(
    (a, b) => ENERGY_ORDER.indexOf(a.bucket) - ENERGY_ORDER.indexOf(b.bucket)
  )

  // Feature description
  const getFeatureDesc = (val: number | null, low: string, high: string) => {
    if (val === null) return '—'
    if (val < 0.35) return low
    if (val > 0.65) return high
    return 'Balanced'
  }

  const hasFeatures = audio_features.energy !== null

  return (
    <div className="dashboard-page">
      <h1>Library Dashboard</h1>

      {/* Top stats */}
      <div className="stat-pills">
        <StatPill label="All Tracks" value={totals.all_tracks.toLocaleString()} accent sub="Liked + playlists + streamed" />
        <StatPill label="Liked Songs" value={totals.liked_songs} />
        <StatPill label="Artists" value={totals.artists} />
        <StatPill label="Albums" value={totals.albums} />
        <StatPill label="Reviewed" value={`${totals.reviewed.toLocaleString()} / ${totals.all_tracks.toLocaleString()}`} sub={`${totals.review_pct}% complete`} />
        <StatPill label="Audio Features" value={totals.with_features.toLocaleString()} sub={totals.with_features === 0 ? 'Not yet fetched' : `of ${totals.all_tracks.toLocaleString()}`} />
      </div>

      {health && (
        <div className="dash-grid">
          <SectionCard title="Library Health Score" className="span-2">
            <HealthScoreCard data={health} />
          </SectionCard>
        </div>
      )}

      <div className="dash-grid">

        {/* Library growth */}
        <SectionCard title="Library Growth" className="span-2">
          {yearly_growth.length > 0 ? (
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={yearly_growth} margin={{ top: 4, right: 8, bottom: 0, left: -20 }}>
                <XAxis dataKey="year" tick={{ fontSize: 11, fill: 'var(--text-muted)' }} />
                <YAxis tick={{ fontSize: 11, fill: 'var(--text-muted)' }} />
                <Tooltip content={<CustomTooltip />} />
                <Bar dataKey="n" name="Songs added" fill="var(--accent)" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="no-data">No timeline data yet</div>
          )}
        </SectionCard>

        {/* Review progress */}
        <SectionCard title="Review Progress">
          {reviewPieData.length > 0 ? (
            <>
              <ResponsiveContainer width="100%" height={180}>
                <PieChart>
                  <Pie
                    data={reviewPieData}
                    cx="50%" cy="50%"
                    innerRadius={50} outerRadius={75}
                    dataKey="value"
                    paddingAngle={2}
                  >
                    {reviewPieData.map((entry, i) => (
                      <Cell key={i} fill={STATUS_COLORS[entry.status] ?? '#666'} />
                    ))}
                  </Pie>
                  <Tooltip formatter={((val: any, name: any) => [Number(val).toLocaleString(), name]) as any} />
                </PieChart>
              </ResponsiveContainer>
              <div className="pie-legend">
                {reviewPieData.map(d => (
                  <div key={d.status} className="pie-legend-item">
                    <div className="pie-dot" style={{ background: STATUS_COLORS[d.status] ?? '#666' }} />
                    <span>{d.name}</span>
                    <span className="pie-count">{d.value.toLocaleString()}</span>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <div className="no-data">Start reviewing to see breakdown</div>
          )}
        </SectionCard>

        {/* Library composition -- how tracks entered the library */}
        <SectionCard title="Library Composition">
          {(() => {
            const compData = [
              { name: 'Liked only', bucketKey: 'liked_only', value: library_composition.liked_only, color: '#f9a8d4' },
              { name: 'Playlist only', bucketKey: 'playlist_only', value: library_composition.playlist_only, color: '#7c5cbf' },
              { name: 'Streamed only', bucketKey: 'streamed_only', value: library_composition.streamed_only, color: '#fbbf24' },
              { name: 'Multiple sources', bucketKey: 'overlapping', value: library_composition.overlapping, color: '#34d399' },
            ].filter(d => d.value > 0)
            return compData.length > 0 ? (
              <>
                <ResponsiveContainer width="100%" height={180}>
                  <PieChart>
                    <Pie data={compData} cx="50%" cy="50%" innerRadius={50} outerRadius={75} dataKey="value" paddingAngle={2}>
                      {compData.map((entry, i) => <Cell key={i} fill={entry.color} />)}
                    </Pie>
                    <Tooltip formatter={((val: any, name: any) => [Number(val).toLocaleString(), name]) as any} />
                  </PieChart>
                </ResponsiveContainer>
                <div className="pie-legend">
                  {compData.map(d => (
                    <div key={d.name} className="pie-legend-item">
                      <div className="pie-dot" style={{ background: d.color }} />
                      <span>{d.name}</span>
                      <span className="pie-count">{d.value.toLocaleString()}</span>
                    </div>
                  ))}
                </div>
                <div className="drilldown-row">
                  {compData.map(d => (
                    <CompositionDrilldown key={d.bucketKey} bucket={d.bucketKey} label={d.name} />
                  ))}
                </div>
              </>
            ) : <div className="no-data">No composition data yet</div>
          })()}
        </SectionCard>


        <SectionCard title="Top Genres" className="span-2">
          {top_genres.length > 0 ? (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={top_genres} layout="vertical" margin={{ top: 0, right: 16, bottom: 0, left: 80 }}>
                <XAxis type="number" tick={{ fontSize: 11, fill: 'var(--text-muted)' }} />
                <YAxis type="category" dataKey="genre" tick={{ fontSize: 11, fill: 'var(--text-muted)' }} width={80} />
                <Tooltip content={<CustomTooltip />} />
                <Bar dataKey="count" name="Tracks" fill="var(--accent-2)" radius={[0, 3, 3, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="no-data">Genre data comes from artist metadata. Import liked songs to populate.</div>
          )}
        </SectionCard>

        {/* Decade breakdown */}
        <SectionCard title="By Decade">
          {decade_breakdown.length > 0 ? (
            <ResponsiveContainer width="100%" height={180}>
              <BarChart data={decade_breakdown} margin={{ top: 4, right: 8, bottom: 0, left: -20 }}>
                <XAxis dataKey="decade" tick={{ fontSize: 11, fill: 'var(--text-muted)' }} />
                <YAxis tick={{ fontSize: 11, fill: 'var(--text-muted)' }} />
                <Tooltip content={<CustomTooltip />} />
                <Bar dataKey="n" name="Tracks" fill="#818cf8" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="no-data">No release date data yet</div>
          )}
        </SectionCard>

        {/* Audio profile radar */}
        <SectionCard title="Sound Profile">
          {hasFeatures ? (
            <>
              <ResponsiveContainer width="100%" height={200}>
                <RadarChart data={radarData}>
                  <PolarGrid stroke="var(--border)" />
                  <PolarAngleAxis dataKey="feature" tick={{ fontSize: 11, fill: 'var(--text-muted)' }} />
                  <Radar name="Your Library" dataKey="value" stroke="var(--accent-2)" fill="var(--accent)" fillOpacity={0.3} />
                  <Tooltip />
                </RadarChart>
              </ResponsiveContainer>
              <div className="feature-descriptions">
                <div className="feat-desc-item">
                  <span>Energy</span>
                  <span className="feat-desc-val">{getFeatureDesc(audio_features.energy, 'Calm & quiet', 'Intense & loud')}</span>
                </div>
                <div className="feat-desc-item">
                  <span>Mood</span>
                  <span className="feat-desc-val">{getFeatureDesc(audio_features.valence, 'Dark & melancholy', 'Bright & happy')}</span>
                </div>
                <div className="feat-desc-item">
                  <span>Danceability</span>
                  <span className="feat-desc-val">{getFeatureDesc(audio_features.danceability, 'Non-rhythmic', 'Very danceable')}</span>
                </div>
              </div>
            </>
          ) : (
            <div className="no-data">Audio features not yet available. Spotify has restricted this API — data will come from your export.</div>
          )}
        </SectionCard>

        {/* Energy distribution */}
        <SectionCard title="Energy Distribution">
          {sortedEnergy.length > 0 ? (
            <div className="energy-bars">
              {sortedEnergy.map(d => (
                <div key={d.bucket} className="energy-row">
                  <span className="energy-label" style={{ color: ENERGY_COLORS[d.bucket] }}>{d.bucket}</span>
                  <div className="energy-track">
                    <div
                      className="energy-fill"
                      style={{
                        width: `${Math.round(d.n / Math.max(...sortedEnergy.map(e => e.n)) * 100)}%`,
                        background: ENERGY_COLORS[d.bucket]
                      }}
                    />
                  </div>
                  <span className="energy-count">{d.n}</span>
                </div>
              ))}
            </div>
          ) : (
            <div className="no-data">Requires audio features data</div>
          )}
        </SectionCard>

        {/* Top artists */}
        <SectionCard title="Top Artists" className="span-2">
          {top_artists.length > 0 ? (
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={top_artists} layout="vertical" margin={{ top: 0, right: 16, bottom: 0, left: 120 }}>
                <XAxis type="number" tick={{ fontSize: 11, fill: 'var(--text-muted)' }} />
                <YAxis type="category" dataKey="artist" tick={{ fontSize: 11, fill: 'var(--text-muted)' }} width={120} />
                <Tooltip content={<CustomTooltip />} />
                <Bar dataKey="n" name="Liked songs" fill="#34d399" radius={[0, 3, 3, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="no-data">No artist data yet</div>
          )}
        </SectionCard>

      </div>

      {/* --- Real Listening Data (from Extended Streaming History) --- */}
      {listening?.available && (
        <>
          <h1 style={{ marginTop: 32 }}>Listening Behaviour</h1>
          <div className="stat-pills">
            <StatPill label="Total Plays" value={listening.overview!.total_plays} accent />
            <StatPill label="Hours Listened" value={listening.overview!.total_hours.toLocaleString()} />
            <StatPill label="Unique Tracks Played" value={listening.overview!.unique_tracks_played} />
            <StatPill label="Skip Rate" value={`${listening.overview!.overall_skip_rate_pct}%`} />
            <StatPill label="Streamed, Never Liked" value={listening.streamed_never_liked ?? 0} sub="Hidden-gem candidates" />
          </div>

          <div className="dash-grid">
            {/* Real listening activity by year, vs. like-dates above */}
            <SectionCard title="Plays Per Year (Actual Listening)" className="span-2">
              {listening.plays_by_year && listening.plays_by_year.length > 0 ? (
                <ResponsiveContainer width="100%" height={200}>
                  <BarChart data={listening.plays_by_year} margin={{ top: 4, right: 8, bottom: 0, left: -20 }}>
                    <XAxis dataKey="year" tick={{ fontSize: 11, fill: 'var(--text-muted)' }} />
                    <YAxis tick={{ fontSize: 11, fill: 'var(--text-muted)' }} />
                    <Tooltip content={<CustomTooltip />} />
                    <Bar dataKey="plays" name="Total plays" fill="var(--accent)" radius={[3, 3, 0, 0]} />
                    <Bar dataKey="real_plays" name="Full plays (>30s)" fill="#34d399" radius={[3, 3, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <div className="no-data">No listening history yet</div>
              )}
            </SectionCard>

            {/* When you actually listen -- day x hour pattern */}
            <SectionCard title="When You Listen" className="span-2">
              {heatmap && heatmap.cells.length > 0 ? (
                <HeatmapGrid cells={heatmap.cells} />
              ) : (
                <div className="no-data">No listening history yet</div>
              )}
            </SectionCard>

            {/* Finer-grained than the yearly chart -- spot seasonal patterns and binges */}
            <SectionCard title="Monthly Listening Trend" className="span-2">
              {monthlyTrend && monthlyTrend.months.length > 0 ? (
                <ResponsiveContainer width="100%" height={200}>
                  <BarChart data={monthlyTrend.months} margin={{ top: 4, right: 8, bottom: 0, left: -20 }}>
                    <XAxis dataKey="month" tick={{ fontSize: 10, fill: 'var(--text-muted)' }} interval={2} />
                    <YAxis tick={{ fontSize: 11, fill: 'var(--text-muted)' }} />
                    <Tooltip content={<CustomTooltip />} />
                    <Bar dataKey="hours" name="Hours listened" fill="var(--accent)" radius={[3, 3, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <div className="no-data">No listening history yet</div>
              )}
            </SectionCard>

            {/* Is skipping concentrated in a few tracks, or spread evenly? */}
            <SectionCard title="Skip Rate Distribution">
              {skipDist && skipDist.buckets.some(b => b.n > 0) ? (
                <ResponsiveContainer width="100%" height={180}>
                  <BarChart data={skipDist.buckets} margin={{ top: 4, right: 8, bottom: 0, left: -20 }}>
                    <XAxis dataKey="bucket" tick={{ fontSize: 10, fill: 'var(--text-muted)' }} />
                    <YAxis tick={{ fontSize: 11, fill: 'var(--text-muted)' }} />
                    <Tooltip content={<CustomTooltip />} />
                    <Bar dataKey="n" name="Tracks" fill="#f87171" radius={[3, 3, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <div className="no-data">No skip data yet</div>
              )}
            </SectionCard>

            {/* Top tracks by actual minutes listened -- not just liked-song count */}
            <SectionCard title="Top Tracks by Listening Time" className="span-2">
              {listening.top_by_listening_time && listening.top_by_listening_time.length > 0 ? (
                <div className="evidence-list">
                  {listening.top_by_listening_time.map((t, i) => (
                    <div key={i} className="evidence-row">
                      <div className="evidence-main">
                        <span className="evidence-name">{t.name}</span>
                        <span className="evidence-sub">{t.artist}</span>
                      </div>
                      <div className="evidence-stats">
                        <span>{t.total_minutes.toLocaleString()} min</span>
                        <span>{t.play_count} plays</span>
                        <span>{t.skip_rate_pct}% skip</span>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="no-data">No listening history yet</div>
              )}
            </SectionCard>

            {/* Forgotten gems: liked, heavily played once, then abandoned */}
            <SectionCard title="Forgotten Favourites" className="span-2">
              {listening.forgotten_favourites && listening.forgotten_favourites.length > 0 ? (
                <div className="evidence-list">
                  {listening.forgotten_favourites.map((t, i) => (
                    <div key={i} className="evidence-row">
                      <div className="evidence-main">
                        <span className="evidence-name">{t.name}</span>
                        <span className="evidence-sub">{t.artist}</span>
                      </div>
                      <div className="evidence-stats">
                        <span>{t.play_count} plays</span>
                        <span>{Math.round(t.days_since_played / 30)} months ago</span>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="no-data">None found -- nothing you loved has gone quiet yet</div>
              )}
            </SectionCard>

            {/* Archive candidates by evidence: liked but consistently skipped */}
            <SectionCard title="Frequently Skipped" className="span-2">
              {listening.high_skip_rate && listening.high_skip_rate.length > 0 ? (
                <div className="evidence-list">
                  {listening.high_skip_rate.map((t, i) => (
                    <div key={i} className="evidence-row">
                      <div className="evidence-main">
                        <span className="evidence-name">{t.name}</span>
                        <span className="evidence-sub">{t.artist}</span>
                      </div>
                      <div className="evidence-stats">
                        <span style={{ color: '#f87171' }}>{t.skip_rate_pct}% skipped</span>
                        <span>{t.total_plays} plays</span>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="no-data">No frequently-skipped liked tracks found</div>
              )}
            </SectionCard>
          </div>
        </>
      )}

      {listening && !listening.available && (
        <div className="no-data" style={{ marginTop: 24 }}>
          Import your Spotify Extended Streaming History (<code>import-history</code>) to unlock
          real listening-behaviour analytics here.
        </div>
      )}
    </div>
  )
}
