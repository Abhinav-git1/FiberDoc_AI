import { useState } from 'react'
import FindingCard from './FindingCard'
import { reportUrl } from './api'
import type { ChatDoc, Decision, Finding, FindingStatus, Project, Severity } from './types'

const STATUS_ORDER: FindingStatus[] = ['failed', 'missing_evidence', 'needs_review', 'passed']
const STATUS_LABEL: Record<FindingStatus, string> = {
  failed: 'Failed',
  missing_evidence: 'Missing evidence',
  needs_review: 'Needs review',
  passed: 'Passed',
}
const SEVERITIES: Severity[] = ['high', 'medium', 'low']

const fmtSize = (b: number) => (b > 1e6 ? `${(b / 1e6).toFixed(1)} MB` : `${Math.max(1, Math.round(b / 1e3))} KB`)
const fmtDuration = (ms: number) => (ms < 60_000 ? `${Math.round(ms / 1000)} s` : `${Math.floor(ms / 60_000)} min ${Math.round((ms % 60_000) / 1000)} s`)

/** Most urgent first: failed, missing evidence, needs review, passed; then by severity. */
function rank(f: Finding) {
  const s = STATUS_ORDER.indexOf(statusOf(f))
  return s * 10 + SEVERITIES.indexOf(f.severity)
}

interface Props {
  doc: ChatDoc
  findings: Finding[]
  projects: Project[]
  onReview: (id: string, decision: Decision, comment: string) => Promise<void>
  onClose: () => void
  goTo: (view: 'findings' | 'review') => void
}

/** Right-hand sidebar for one uploaded document: the response, document details, and its findings. */
export default function ResultPanel({ doc, findings, projects, onReview, onClose, goTo }: Props) {
  const [tab, setTab] = useState<'results' | 'text'>('results')
  const [hidePassed, setHidePassed] = useState(true)
  const [category, setCategory] = useState<string | null>(null)
  const s = doc.server
  const mine = s?.documentId ? findings.filter((f) => f.documentId === s.documentId).sort((a, b) => rank(a) - rank(b)) : []
  const categories = byCategory(mine)
  const inCategory = category ? mine.filter((f) => categoryOf(f) === category) : mine
  const shown = hidePassed ? inCategory.filter((f) => f.status !== 'passed') : inCategory
  const project = projects.find((p) => p.id === s?.projectId)
  const pending = mine.filter((f) => f.decision === 'pending').length

  return (
    <aside className="docpanel">
      <div className="docpanel-head">
        <div>
          <strong>{doc.name}</strong>
          <div className="muted">{s ? <PhaseLabel doc={doc} /> : 'Not sent to the server'}</div>
        </div>
        <button className="icon-btn" onClick={onClose} aria-label="Close panel">×</button>
      </div>

      <div className="panel-tabs" role="tablist">
        <button role="tab" aria-selected={tab === 'results'} className={tab === 'results' ? 'active' : ''} onClick={() => setTab('results')}>
          Results{mine.length > 0 && <span className="count">{mine.length}</span>}
        </button>
        <button role="tab" aria-selected={tab === 'text'} className={tab === 'text' ? 'active' : ''} onClick={() => setTab('text')}>
          Extracted text
        </button>
      </div>

      <div className="docpanel-body">
        {tab === 'text' && <TextTab doc={doc} />}

        {tab === 'results' && !s && <p className="muted">Select a project and attach the document again to run the rule checks.</p>}

        {tab === 'results' && s && (
          <>
            {(s.phase === 'uploading' || s.phase === 'processing') && (
              <div className="progress indeterminate">
                <div className="bar"><div /></div>
                <span>{s.phase === 'uploading' ? 'Uploading…' : 'Extracting text and running the rule checks…'}</span>
              </div>
            )}

            {s.response && (
              <section className="panel-section">
                <h4>Response</h4>
                <p className={s.phase === 'error' ? 'err' : ''}>{s.response}</p>
              </section>
            )}

            <section className="panel-section">
              <h4>Details</h4>
              <dl className="details">
                <dt>Project</dt><dd>{project?.name ?? '-'}</dd>
                <dt>Document type</dt><dd>{s.doc ? s.doc.docType.replace(/_/g, ' ') : '-'}</dd>
                <dt>Pages</dt><dd>{s.doc?.pageCount || '-'}</dd>
                <dt>Size</dt><dd>{doc.size ? fmtSize(doc.size) : '-'}</dd>
                <dt>Processing time</dt><dd>{s.finishedAt ? fmtDuration(s.finishedAt - s.startedAt) : '-'}</dd>
                <dt>SHA-256</dt><dd className="mono" title={s.doc?.sha256 ?? ''}>{s.doc?.sha256 ? `${s.doc.sha256.slice(0, 16)}…` : '-'}</dd>
                <dt>Document ID</dt><dd className="mono">{s.documentId ?? '-'}</dd>
              </dl>
            </section>

            {mine.length > 0 && (
              <>
                <section className="panel-section">
                  <h4>Summary</h4>
                  <div className="stat-row">
                    {STATUS_ORDER.map((st) => (
                      <div key={st} className={`stat status-${st}`}>
                        <span className="stat-num">{mine.filter((f) => statusOf(f) === st).length}</span>
                        <span className="stat-label">{STATUS_LABEL[st]}</span>
                      </div>
                    ))}
                  </div>
                  <p className="muted">
                    Severity: {SEVERITIES.map((sv) => `${mine.filter((f) => f.severity === sv && f.status !== 'passed').length} ${sv}`).join(' · ')}
                    {' '}(excluding passed) · {pending} of {mine.length} awaiting review
                  </p>
                  <div className="panel-actions">
                    <button className="chip" onClick={() => goTo('review')}>Open review queue →</button>
                    <button className="chip" onClick={() => goTo('findings')}>All findings →</button>
                    <a className="chip" href={reportUrl(s.projectId)}>Download project report</a>
                  </div>
                </section>

                <section className="panel-section">
                  <div className="panel-section-head">
                    <h4>By category</h4>
                    {category && <button className="chip" onClick={() => setCategory(null)}>Show all</button>}
                  </div>
                  <div className="cat-list">
                    {categories.map(({ name, counts, total }) => (
                      <button key={name} className={'cat-row' + (category === name ? ' active' : '')} aria-pressed={category === name}
                        title={STATUS_ORDER.map((st) => `${counts[st]} ${STATUS_LABEL[st].toLowerCase()}`).join(', ')}
                        onClick={() => setCategory(category === name ? null : name)}>
                        <span className="cat-name">{name}</span>
                        <span className="cat-bar" aria-hidden>
                          {STATUS_ORDER.map((st) => counts[st] > 0 && (
                            <span key={st} className={`seg status-${st}`} style={{ flexGrow: counts[st] }} />
                          ))}
                        </span>
                        <span className="cat-count">{total - counts.passed ? `${total - counts.passed} open` : 'all passed'} · {total}</span>
                      </button>
                    ))}
                  </div>
                </section>

                <section className="panel-section">
                  <div className="panel-section-head">
                    <h4>Findings{category ? ` · ${category}` : ''}</h4>
                    <label className="muted toggle">
                      <input type="checkbox" checked={hidePassed} onChange={(e) => setHidePassed(e.target.checked)} /> Hide passed
                    </label>
                  </div>
                  {shown.length === 0 && <p className="muted">No open issues: every checked rule passed.</p>}
                  {shown.map((f) => <FindingCard key={f.id} finding={f} onReview={onReview} />)}
                </section>
              </>
            )}

            {s.phase === 'done' && mine.length === 0 && <p className="muted">No findings were recorded for this document.</p>}
          </>
        )}
      </div>
    </aside>
  )
}

const categoryOf = (f: Finding) => f.ruleSection ?? 'Other'
/** Findings from before statuses existed have none; they were never settled automatically, so: needs review. */
const statusOf = (f: Finding): FindingStatus => f.status ?? 'needs_review'

/** Findings grouped by rule category, most open issues first. */
function byCategory(fs: Finding[]) {
  const groups = new Map<string, Record<FindingStatus, number>>()
  for (const f of fs) {
    const c = groups.get(categoryOf(f)) ?? { failed: 0, missing_evidence: 0, needs_review: 0, passed: 0 }
    c[statusOf(f)]++
    groups.set(categoryOf(f), c)
  }
  return [...groups].map(([name, counts]) => ({ name, counts, total: Object.values(counts).reduce((a, b) => a + b, 0) }))
    .sort((a, b) => (b.total - b.counts.passed) - (a.total - a.counts.passed) || a.name.localeCompare(b.name))
}

function PhaseLabel({ doc }: { doc: ChatDoc }) {
  const s = doc.server!
  switch (s.phase) {
    case 'uploading': return <>Uploading…</>
    case 'processing': return <>Processing…</>
    case 'error': return <span className="err">Failed</span>
    case 'timeout': return <>Still processing (check the Findings page later)</>
    default: return <>Checked · awaiting review</>
  }
}

function TextTab({ doc }: { doc: ChatDoc }) {
  if (doc.status === 'processing') {
    return (
      <div className="progress">
        <div className="bar"><div style={{ width: `${Math.round(doc.progress * 100)}%` }} /></div>
        <span>{doc.label} · {Math.round(doc.progress * 100)}%</span>
      </div>
    )
  }
  if (doc.status === 'error') return <p className="err">Text preview failed: {doc.error}</p>
  if (!doc.file) {
    return <p className="muted">The browser text preview is only available in the session the file was uploaded in. The server keeps the original and its extracted text for the checks.</p>
  }
  return (
    <>
      <p className="muted">
        Preview read in your browser{doc.pages ? ` · ${doc.pages} page(s)` : ''}{doc.method && doc.method !== 'server' ? ` · ${doc.method}` : ''}.
        The server extracts the document separately for the rule checks.
      </p>
      <pre>{doc.text || '(No text detected)'}</pre>
    </>
  )
}
