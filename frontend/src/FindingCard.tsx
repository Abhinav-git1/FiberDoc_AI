import { useState } from 'react'
import type { Decision, Finding } from './types'

export const DECISION_LABEL: Record<Decision, string> = {
  pending: 'Pending review',
  approved: 'Accepted',
  rejected: 'Rejected',
  changes_requested: 'Changes requested',
}

interface Props {
  finding: Finding
  onReview: (id: string, decision: Decision, comment: string) => Promise<void>
  defaultOpen?: boolean
}

/** Explainable finding: rule, quoted evidence, reasoning, and reviewer actions. */
export default function FindingCard({ finding: f, onReview, defaultOpen = false }: Props) {
  const [open, setOpen] = useState(defaultOpen)
  const [comment, setComment] = useState('')
  const [busy, setBusy] = useState(false)

  async function decide(d: Decision) {
    setBusy(true)
    try { await onReview(f.id, d, comment); setComment('') } finally { setBusy(false) }
  }

  return (
    <article className={`finding sev-${f.severity}`}>
      <button className="finding-head" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        <span className={`badge sev ${f.severity}`}>{f.severity}</span>
        <span className="finding-title">{f.title}</span>
        <span className={`badge dec ${f.decision}`}>{DECISION_LABEL[f.decision]}</span>
        <span className="chev">{open ? '▾' : '▸'}</span>
      </button>
      <div className="muted finding-sub">{f.docName} · Rule {f.ruleId}</div>

      {open && (
        <div className="finding-body">
          <section>
            <h4>Rule</h4>
            <p>{f.ruleText}</p>
          </section>
          <section>
            <h4>Evidence</h4>
            {f.evidence ? (
              <blockquote>“{f.evidence.quote}” <span className="muted">— page {f.evidence.page}</span></blockquote>
            ) : (
              <p className="missing">Required evidence not found in the document.</p>
            )}
          </section>
          <section>
            <h4>
              Why flagged{' '}
              <span className={`badge src ${f.source}`}>{f.source === 'rule' ? 'Rule check' : 'AI interpretation'}</span>
            </h4>
            <p>{f.explanation}</p>
          </section>

          {f.comments.length > 0 && (
            <section>
              <h4>Comments</h4>
              {f.comments.map((c) => (
                <p key={c.id} className="comment"><strong>{c.author}</strong> <span className="muted">{c.at}</span><br />{c.text}</p>
              ))}
            </section>
          )}

          <div className="review-box">
            <textarea rows={2} value={comment} placeholder="Add a comment (optional)…" onChange={(e) => setComment(e.target.value)} />
            <div className="review-actions">
              <button className="btn ok" disabled={busy} onClick={() => decide('approved')}>Accept</button>
              <button className="btn warn" disabled={busy} onClick={() => decide('changes_requested')}>Request changes</button>
              <button className="btn bad" disabled={busy} onClick={() => decide('rejected')}>Reject</button>
            </div>
          </div>
        </div>
      )}
    </article>
  )
}
