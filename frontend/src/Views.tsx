import { useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import FindingCard from './FindingCard'
import { reportUrl } from './api'
import type { Decision, Finding, Project, Severity } from './types'

type Review = (id: string, decision: Decision, comment: string) => Promise<void>

function NewProjectForm({ onCreate }: { onCreate: (name: string, location: string) => Promise<void> }) {
  const [name, setName] = useState('')
  const [location, setLocation] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (!name.trim()) return
    setBusy(true)
    setError('')
    try {
      await onCreate(name.trim(), location.trim())
      setName('')
      setLocation('')
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="new-project" onSubmit={submit}>
      <input placeholder="Project name" value={name} onChange={(e) => setName(e.target.value)} required />
      <input placeholder="Location (optional)" value={location} onChange={(e) => setLocation(e.target.value)} />
      <button type="submit" disabled={busy || !name.trim()}>{busy ? 'Creating…' : '＋ New project'}</button>
      {error && <span className="err">{error}</span>}
    </form>
  )
}

export function DashboardView({ projects, findings, onOpenProject, onCreateProject }: {
  projects: Project[]; findings: Finding[]; onOpenProject: (id: string) => void
  onCreateProject: (name: string, location: string) => Promise<void>
}) {
  return (
    <div className="page">
      <h2>Projects</h2>
      <NewProjectForm onCreate={onCreateProject} />
      {projects.length === 0 && <p className="muted">No projects yet. Create one above, then upload a document in Chat.</p>}
      <div className="cards">
        {projects.map((p) => {
          const fs = findings.filter((f) => f.projectId === p.id)
          const count = (s: Severity) => fs.filter((f) => f.severity === s && f.decision === 'pending').length
          const pending = fs.filter((f) => f.decision === 'pending').length
          return (
            <button key={p.id} className="project-card" onClick={() => onOpenProject(p.id)}>
              <strong>{p.name}</strong>
              <span className="muted">{p.location} · {p.docCount} documents</span>
              <div className="stats">
                <span className="badge sev high">{count('high')} high</span>
                <span className="badge sev medium">{count('medium')} medium</span>
                <span className="badge sev low">{count('low')} low</span>
              </div>
              <span className="muted">{pending} awaiting review</span>
            </button>
          )
        })}
      </div>
    </div>
  )
}

export function FindingsView({ projects, findings, onReview, projectId, setProjectId }: {
  projects: Project[]; findings: Finding[]; onReview: Review; projectId: string; setProjectId: (id: string) => void
}) {
  const [sev, setSev] = useState<'all' | Severity>('all')
  const shown = useMemo(
    () => findings.filter((f) => (!projectId || f.projectId === projectId) && (sev === 'all' || f.severity === sev)),
    [findings, projectId, sev],
  )
  const docs = [...new Set(shown.map((f) => f.docName))]

  return (
    <div className="page">
      <h2>Findings report</h2>
      <div className="filters">
        <select value={projectId} onChange={(e) => setProjectId(e.target.value)}>
          <option value="">All projects</option>
          {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
        <select value={sev} onChange={(e) => setSev(e.target.value as 'all' | Severity)}>
          <option value="all">All severities</option>
          <option value="high">High</option>
          <option value="medium">Medium</option>
          <option value="low">Low</option>
        </select>
        <span className="muted">{shown.length} finding(s)</span>
        {projectId
          ? <a className="download" href={reportUrl(projectId)}>⬇ Download report</a>
          : <span className="muted">Select a project to download its report</span>}
      </div>
      {docs.length === 0 && <p className="muted">No findings match.</p>}
      {docs.map((d) => (
        <section key={d} className="doc-group">
          <h3>📄 {d}</h3>
          {shown.filter((f) => f.docName === d).map((f) => <FindingCard key={f.id} finding={f} onReview={onReview} />)}
        </section>
      ))}
      <p className="muted note">Findings come from the backend rule workflow. AI-assisted findings must be confirmed by a human reviewer.</p>
    </div>
  )
}

export function ReviewQueueView({ findings, onReview }: { findings: Finding[]; onReview: Review }) {
  const queue = findings.filter((f) => f.decision === 'pending')
  const done = findings.filter((f) => f.decision !== 'pending')
  return (
    <div className="page">
      <h2>Review queue <span className="muted">({queue.length} pending)</span></h2>
      {queue.length === 0 && <p className="muted">Nothing waiting for review. 🎉</p>}
      {queue.map((f) => <FindingCard key={f.id} finding={f} onReview={onReview} defaultOpen />)}
      {done.length > 0 && (
        <>
          <h3 className="history-h">Reviewed</h3>
          {done.map((f) => <FindingCard key={f.id} finding={f} onReview={onReview} />)}
        </>
      )}
    </div>
  )
}
