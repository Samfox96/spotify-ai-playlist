import { useState, useEffect } from 'react'
import { getAuthStatus, importLikedSongs, importAudioFeatures, importPlaylists, getImportHistory } from './services/api'
import ReviewQueue from './pages/ReviewQueue'
import Dashboard from './pages/Dashboard'
import Discovery from './pages/Discovery'
import './App.css'

type Tab = 'dashboard' | 'review' | 'discovery' | 'import'

export default function App() {
  const [tab, setTab] = useState<Tab>('review')
  const [user, setUser] = useState<any>(null)
  const [importing, setImporting] = useState<string | null>(null)
  const [importLog, setImportLog] = useState<string[]>([])
  const [importHistory, setImportHistory] = useState<any[]>([])

  useEffect(() => {
    getAuthStatus().then(d => { if (d.authenticated) setUser(d.user) }).catch(() => {})
  }, [])

  const runImport = async (type: 'liked' | 'features' | 'playlists', full = false) => {
    setImporting(type)
    setImportLog([`Starting ${type === 'liked' ? 'liked songs' : type === 'features' ? 'audio features' : 'playlists'} import...`])
    try {
      const result = type === 'liked'
        ? await importLikedSongs(!full)
        : type === 'features'
        ? await importAudioFeatures()
        : await importPlaylists()
      const c = result.counts
      setImportLog(prev => [...prev, `Done: ${c.found ?? c.processed ?? c.playlists ?? 0} processed | ${c.new ?? c.success ?? c.tracks_new_or_updated ?? 0} new | ${c.errors} errors`])
      getImportHistory().then(setImportHistory)
    } catch (e: any) {
      setImportLog(prev => [...prev, `Error: ${e.response?.data?.error || e.message}`])
    } finally {
      setImporting(null)
    }
  }

  useEffect(() => {
    if (tab === 'import') getImportHistory().then(setImportHistory).catch(() => {})
  }, [tab])

  return (
    <div className="app">
      <nav className="nav">
        <div className="nav-brand">
          <span className="nav-icon">♬</span>
          <span className="nav-title">Music Intelligence</span>
        </div>
        <div className="nav-tabs">
          <button className={`nav-tab ${tab === 'dashboard' ? 'active' : ''}`} onClick={() => setTab('dashboard')}>Dashboard</button>
          <button className={`nav-tab ${tab === 'review' ? 'active' : ''}`} onClick={() => setTab('review')}>⚡ Review Queue</button>
          <button className={`nav-tab ${tab === 'discovery' ? 'active' : ''}`} onClick={() => setTab('discovery')}>🔍 Discovery</button>
          <button className={`nav-tab ${tab === 'import' ? 'active' : ''}`} onClick={() => setTab('import')}>Import</button>
        </div>
        {user && (
          <div className="nav-user">
            {user.image_url && <img src={user.image_url} alt="" className="nav-avatar" />}
            <span>{user.display_name}</span>
          </div>
        )}
      </nav>

      <main className="main">
        {tab === 'dashboard' && <Dashboard />}
        {tab === 'review' && <ReviewQueue onStatsChange={() => {}} />}
        {tab === 'discovery' && <Discovery />}
        {tab === 'import' && (
          <div className="import-page">
            <h1>Data Import</h1>
            <div className="import-cards">
              <div className="import-card">
                <h2>Liked Songs</h2>
                <p>Pull your saved tracks from Spotify into the local database.</p>
                <div className="btn-row">
                  <button className="btn btn-primary" disabled={!!importing} onClick={() => runImport('liked', false)}>
                    {importing === 'liked' ? 'Importing…' : 'Incremental Sync'}
                  </button>
                  <button className="btn btn-secondary" disabled={!!importing} onClick={() => runImport('liked', true)}>Full Re-import</button>
                </div>
              </div>
              <div className="import-card">
                <h2>Audio Features</h2>
                <p>Fetch energy, valence, tempo, danceability for all tracks.</p>
                <div className="btn-row">
                  <button className="btn btn-primary" disabled={!!importing} onClick={() => runImport('features')}>
                    {importing === 'features' ? 'Fetching…' : 'Fetch Features'}
                  </button>
                </div>
              </div>
              <div className="import-card">
                <h2>Playlists</h2>
                <p>Import all your playlists and their tracks, with full metadata.</p>
                <div className="btn-row">
                  <button className="btn btn-primary" disabled={!!importing} onClick={() => runImport('playlists')}>
                    {importing === 'playlists' ? 'Importing…' : 'Import Playlists'}
                  </button>
                </div>
              </div>
            </div>
            {importLog.length > 0 && (
              <div className="import-log">
                <h3>Log</h3>
                {importLog.map((line, i) => <div key={i} className="log-line">{line}</div>)}
              </div>
            )}
            {importHistory.length > 0 && (
              <div className="section">
                <h2>Import History</h2>
                <table className="history-table">
                  <thead><tr><th>Type</th><th>Status</th><th>Found</th><th>New</th><th>Started</th></tr></thead>
                  <tbody>
                    {importHistory.map(row => (
                      <tr key={row.id}>
                        <td>{row.import_type}</td>
                        <td><span className={`status-badge status-${row.status}`}>{row.status}</span></td>
                        <td>{row.tracks_found}</td>
                        <td>{row.tracks_new}</td>
                        <td>{new Date(row.started_at).toLocaleString()}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  )
}
