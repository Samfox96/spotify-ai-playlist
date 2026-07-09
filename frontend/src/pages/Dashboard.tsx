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
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    axios.get('/api/dashboard/overview')
      .then(r => setData(r.data))
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="dash-loading"><div className="spinner" /> Loading dashboard...</div>
  if (error) return <div className="dash-error">Failed to load: {error}</div>
  if (!data) return null

  const { totals, yearly_growth, top_genres, audio_features, review_breakdown,
          decade_breakdown, top_artists, energy_distribution } = data

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
        <StatPill label="Liked Songs" value={totals.liked_songs} accent />
        <StatPill label="Artists" value={totals.artists} />
        <StatPill label="Albums" value={totals.albums} />
        <StatPill label="Reviewed" value={`${totals.reviewed.toLocaleString()} / ${totals.liked_songs.toLocaleString()}`} sub={`${totals.review_pct}% complete`} />
        <StatPill label="Audio Features" value={totals.with_features.toLocaleString()} sub={totals.with_features === 0 ? 'Not yet fetched' : `of ${totals.liked_songs.toLocaleString()}`} />
      </div>

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
                  <Tooltip formatter={(val: number, name: string) => [val.toLocaleString(), name]} />
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

        {/* Top genres */}
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
    </div>
  )
}
