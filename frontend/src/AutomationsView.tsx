import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { getAutomationSettings, listDeliveries, rotateAutomationSecret, saveAutomationSettings, sendAutomationTest } from './api'
import type { AutomationSettings, Delivery } from './types'

/** Where the data goes, step by step. `sent` marks what leaves this computer. */
const FLOW: { title: string; detail: string; sent?: string }[] = [
  { title: 'You upload a document', detail: 'Chat & upload. The original is stored on this computer (backend/data/uploads).' },
  { title: 'FiberDoc checks it', detail: 'Text extraction and the rule checks run in the backend.',
    sent: 'Document text goes to Gemini (Google) for embeddings and the AI-checked rules' },
  { title: 'Results are saved', detail: 'Postgres database "fiberdoc": the document, findings, chat message and audit log.' },
  { title: 'Webhook to n8n', detail: 'FiberDoc POSTs a summary to your n8n workflow, with the shared token and a signature.',
    sent: 'Summary only: name, type, counts, open findings and a link. Never the document text' },
  { title: 'n8n: optional Think → Act agent', detail: 'With the Think → Act workflow, two Gemini agents read the open findings and write ordered next steps (skipped when nothing is open).',
    sent: 'The summary (not the document) goes to Gemini from n8n: 2 requests per email' },
  { title: 'n8n sends the email', detail: 'Your workflow formats the summary (and any next steps) and sends it through your email account (SMTP).',
    sent: "The email goes through your email provider's mail server" },
  { title: 'Inbox', detail: 'The recipient below gets the email.' },
]

const fmtTime = (iso: string) => new Date(iso).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })

export default function AutomationsView() {
  const [settings, setSettings] = useState<AutomationSettings | null>(null)
  const [enabled, setEnabled] = useState(false)
  const [url, setUrl] = useState('')
  const [email, setEmail] = useState('')
  const [deliveries, setDeliveries] = useState<Delivery[]>([])
  const [showSecret, setShowSecret] = useState(false)
  const [busy, setBusy] = useState<'' | 'save' | 'test' | 'secret'>('')
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)
  const [loadError, setLoadError] = useState('')

  function apply(s: AutomationSettings) {
    setSettings(s)
    setEnabled(s.enabled)
    setUrl(s.webhookUrl ?? '')
    setEmail(s.recipientEmail ?? '')
  }

  const reloadLog = () => listDeliveries().then(setDeliveries).catch(() => {})

  useEffect(() => {
    getAutomationSettings().then(apply).catch((e: Error) => setLoadError(e.message))
    reloadLog()
    const t = setInterval(reloadLog, 10_000) // new deliveries appear as documents finish
    return () => clearInterval(t)
  }, [])

  const dirty = !!settings && (enabled !== settings.enabled || url.trim() !== (settings.webhookUrl ?? '') || email.trim() !== (settings.recipientEmail ?? ''))

  async function run(kind: 'save' | 'test' | 'secret', fn: () => Promise<string>) {
    setBusy(kind)
    setMsg(null)
    try {
      setMsg({ ok: true, text: await fn() })
    } catch (e) {
      setMsg({ ok: false, text: e instanceof Error ? e.message : String(e) })
    } finally {
      setBusy('')
      reloadLog()
    }
  }

  const save = (e?: FormEvent) => {
    e?.preventDefault()
    return run('save', async () => {
      apply(await saveAutomationSettings({ enabled, webhookUrl: url.trim() || null, recipientEmail: email.trim() || null }))
      return enabled ? 'Saved. Each checked document will now be sent to n8n.' : 'Saved. Automations are switched off.'
    })
  }

  const test = () => run('test', async () => {
    if (dirty) apply(await saveAutomationSettings({ enabled, webhookUrl: url.trim() || null, recipientEmail: email.trim() || null }))
    const d = await sendAutomationTest()
    if (d.status !== 'sent') throw new Error(`Test failed after ${d.attempts} attempt${d.attempts > 1 ? 's' : ''}: ${d.error}`)
    return `Test sent (HTTP ${d.httpStatus}). Check ${email.trim() || 'the inbox'} for the email.`
  })

  const rotate = () => {
    if (!confirm('Create a new token? The old one stops working, so update the Header Auth credential in n8n too.')) return
    run('secret', async () => {
      apply(await rotateAutomationSecret())
      setShowSecret(true)
      return 'New token created. Paste it into the n8n Header Auth credential.'
    })
  }

  return (
    <div className="page automations">
      <h2>Automations</h2>
      <p className="muted">
        When a document has been checked, FiberDoc can send a summary to an <strong>n8n</strong> workflow, which emails it.
        The checking itself always stays in FiberDoc. Setup files and a step-by-step guide: <code>integrations/n8n/</code>.
      </p>
      {loadError && <div className="banner err">{loadError}</div>}

      <section className="auto-section">
        <h3>Where the data goes</h3>
        <ol className="flow">
          {FLOW.map((s, i) => (
            <li key={i} className={'flow-step' + (i >= 3 ? ' flow-new' : '')}>
              <span className="flow-num">{i + 1}</span>
              <div>
                <strong>{s.title}</strong>
                <div className="muted">{s.detail}</div>
                {s.sent && <div className="flow-sent">↗ Leaves this computer: {s.sent}</div>}
              </div>
            </li>
          ))}
        </ol>
        <p className="muted">Steps 4 to 7 only happen when automations are switched on below. Step 5 only with the Think → Act workflow.</p>
      </section>

      <section className="auto-section">
        <h3>Email after each upload</h3>
        <form className="auto-form" onSubmit={save}>
          <label className="auto-switch">
            <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
            <span>Send a summary when a document has been checked</span>
          </label>
          <label>
            <span>n8n webhook URL</span>
            <input type="url" placeholder="http://localhost:5678/webhook/fiberdoc-checked" value={url} onChange={(e) => setUrl(e.target.value)} />
            <small className="muted">From the Webhook node in n8n (Production URL). The workflow must be active.</small>
          </label>
          <label>
            <span>Send the email to</span>
            <input type="email" placeholder="you@example.com" value={email} onChange={(e) => setEmail(e.target.value)} />
          </label>
          <div className="auto-token">
            <span>Shared token</span>
            <div className="auto-token-row">
              <code className="mono">{settings ? (showSecret ? settings.secret : '•'.repeat(24)) : '…'}</code>
              <button type="button" className="btn" onClick={() => setShowSecret((v) => !v)}>{showSecret ? 'Hide' : 'Show'}</button>
              <button type="button" className="btn" disabled={!settings}
                onClick={() => settings && navigator.clipboard.writeText(settings.secret).then(() => setMsg({ ok: true, text: 'Token copied.' }))}>Copy</button>
              <button type="button" className="btn" disabled={busy !== ''} onClick={rotate}>New token</button>
            </div>
            <small className="muted">
              Sent as the <code>X-FiberDoc-Token</code> header. In n8n, set the Webhook node's authentication to Header Auth
              with that name and this value, so only FiberDoc can trigger the workflow.
            </small>
          </div>
          <div className="auto-actions">
            <button type="submit" className="btn primary" disabled={busy !== '' || !dirty}>{busy === 'save' ? 'Saving…' : 'Save'}</button>
            <button type="button" className="btn" disabled={busy !== '' || !url.trim()} onClick={test}>{busy === 'test' ? 'Sending…' : 'Send test'}</button>
            {msg && <span className={msg.ok ? 'ok' : 'err'}>{msg.text}</span>}
          </div>
        </form>
      </section>

      <section className="auto-section">
        <div className="panel-section-head">
          <h3>Delivery log</h3>
          <button className="btn" onClick={reloadLog}>Refresh</button>
        </div>
        {deliveries.length === 0 ? (
          <p className="muted">Nothing sent yet. Use "Send test", or switch automations on and upload a document.</p>
        ) : (
          <div className="table-wrap">
            <table className="deliveries">
              <thead>
                <tr><th>When</th><th>Event</th><th>Status</th><th>Attempts</th><th>Details</th></tr>
              </thead>
              <tbody>
                {deliveries.map((d) => (
                  <tr key={d.id}>
                    <td>{fmtTime(d.createdAt)}</td>
                    <td>{d.event === 'test' ? 'Test' : d.documentName ?? 'Document (deleted)'}</td>
                    <td><span className={`badge delivery-${d.status}`}>{d.status === 'sent' ? `Sent · ${d.httpStatus}` : 'Failed'}</span></td>
                    <td>{d.attempts}</td>
                    <td className="muted" title={d.url}>{d.error ?? 'Delivered to n8n'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="muted">"Sent" means n8n accepted the request. Whether the email went out is shown in n8n under Executions.</p>
      </section>
    </div>
  )
}
