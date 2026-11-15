import { useEffect, useRef, useState } from 'react'
import type { Dispatch, SetStateAction } from 'react'
import { extractText } from './ocr'
import { createChat, getChat, listDocuments, postMessage, uploadDocument } from './api'
import ResultPanel from './ResultPanel'
import { fromSaved, stillProcessing } from './savedChat'
import type { BackendDoc, Chat, ChatDoc, Decision, Finding, Project, ServerResult } from './types'

/** The backend accepts PDF, DOCX and XLSX (see backend/app/services/document_parser.py). */
const UPLOAD_EXTENSIONS = ['.pdf', '.docx', '.xlsx']
const isUploadable = (f: File) => UPLOAD_EXTENSIONS.some((ext) => f.name.toLowerCase().endsWith(ext))
const isPdf = (f: File) => f.name.toLowerCase().endsWith('.pdf')
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))

export const uid = () => Math.random().toString(36).slice(2, 10)
export const newChat = (): Chat => ({ id: uid(), title: 'New chat', messages: [], docs: [] })
const fmtSize = (b: number) => (b > 1e6 ? `${(b / 1e6).toFixed(1)} MB` : `${Math.max(1, Math.round(b / 1e3))} KB`)

const SUGGESTIONS = [
  'Which required fields are missing in this document?',
  'Summarize the splice and fiber count details',
  'List evidence needed for construction sign-off',
]

interface Props {
  chats: Chat[]
  setChats: Dispatch<SetStateAction<Chat[]>>
  activeId: string
  projects: Project[]
  uploadProjectId: string
  setUploadProjectId: (id: string) => void
  /** Reload projects + findings from the backend; resolves with the fresh findings. */
  refresh: () => Promise<Finding[]>
  goTo: (view: 'findings' | 'review') => void
  /** All findings (kept fresh by App), so reviews made in the panel show up everywhere. */
  findings: Finding[]
  onReview: (id: string, decision: Decision, comment: string) => Promise<void>
}

export default function ChatView({ chats, setChats, activeId, projects, uploadProjectId, setUploadProjectId, refresh, goTo, findings, onReview }: Props) {
  const [input, setInput] = useState('')
  const [pending, setPending] = useState<{ id: string; file: File }[]>([])
  const [viewDoc, setViewDoc] = useState<string | null>(null)
  const [dragging, setDragging] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)
  const endRef = useRef<HTMLDivElement>(null)
  const taRef = useRef<HTMLTextAreaElement>(null)
  /** Chats being created on the server, so two quick sends don't create two. */
  const savingRef = useRef(new Map<string, Promise<string | undefined>>())

  const chat = chats.find((c) => c.id === activeId)!
  const patchChat = (id: string, fn: (c: Chat) => Chat) => setChats((cs) => cs.map((c) => (c.id === id ? fn(c) : c)))
  const patchDoc = (chatId: string, docId: string, patch: Partial<ChatDoc>) =>
    patchChat(chatId, (c) => ({ ...c, docs: c.docs.map((d) => (d.id === docId ? { ...d, ...patch } : d)) }))
  const patchServer = (chatId: string, docId: string, patch: Partial<ServerResult>) =>
    patchChat(chatId, (c) => ({
      ...c, docs: c.docs.map((d) => (d.id === docId && d.server ? { ...d, server: { ...d.server, ...patch } } : d)),
    }))

  useEffect(() => { setViewDoc(null); setPending([]) }, [activeId])

  // A saved chat opened from the sidebar: fetch its messages and documents once.
  useEffect(() => {
    if (!chat.serverId || chat.loaded !== false) return
    const { id, serverId } = chat
    let cancelled = false
    getChat(serverId)
      .then((saved) => { if (!cancelled) setChats((cs) => cs.map((c) => (c.id === id ? fromSaved(saved) : c))) })
      .catch((e: Error) => {
        if (!cancelled) patchChat(id, (c) => ({ ...c, loaded: true, messages: [{ id: uid(), role: 'assistant', text: `Could not load this chat: ${e.message}` }] }))
      })
    return () => { cancelled = true }
  }, [chat.id, chat.loaded]) // eslint-disable-line react-hooks/exhaustive-deps

  // A reopened chat whose document is still being checked: nothing in this tab is polling it, so check every 5 s
  // and take the saved result once it's there. Documents sent in this session are watched by submitToBackend.
  const reopenedBusy = !!chat.serverId && chat.docs.some((d) => !d.file && d.server?.phase === 'processing')
  useEffect(() => {
    if (!reopenedBusy || !chat.serverId) return
    const { id, serverId } = chat
    const t = setInterval(async () => {
      const raw = await getChat(serverId).catch(() => null)
      if (!raw) return
      const saved = fromSaved(raw)
      if (stillProcessing(saved)) return
      setChats((cs) => cs.map((c) => c.id !== id ? c : {
        ...c,
        docs: c.docs.map((d) => (d.file ? d : saved.docs.find((x) => x.id === d.id) ?? d)),
        messages: [...c.messages, ...saved.messages.filter((m) => m.resultDocId && !c.docs.find((d) => d.id === m.resultDocId)?.file
          && !c.messages.some((x) => x.id === m.id))],
      }))
      refresh().catch(() => {})
    }, 5000)
    return () => clearInterval(t)
  }, [reopenedBusy, chat.id]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [chat.messages.length])
  useEffect(() => {
    const ta = taRef.current
    if (!ta) return
    ta.style.height = 'auto'
    ta.style.height = Math.min(ta.scrollHeight, 200) + 'px'
  }, [input])

  function addFiles(list: FileList | null) {
    if (!list) return
    const files = [...list].filter(isUploadable)
    if (files.length) setPending((p) => [...p, ...files.map((f) => ({ id: uid(), file: f }))])
  }

  const say = (chatId: string, text: string, resultDocId?: string) =>
    patchChat(chatId, (c) => ({ ...c, messages: [...c.messages, { id: uid(), role: 'assistant', text, resultDocId }] }))
  /** An assistant message the backend doesn't write itself; saved so it's there when the chat is reopened. */
  const sayAndSave = (chatId: string, serverId: string | undefined, text: string) => {
    say(chatId, text)
    if (serverId) postMessage(serverId, 'assistant', text).catch(() => {})
  }

  /** Save the chat on the server on its first message. Resolves to its server ID, or undefined if that failed
   * (the chat then works as before, in this tab only). */
  function ensureSaved(c: Chat, title: string, projectId: string): Promise<string | undefined> {
    if (c.serverId) return Promise.resolve(c.serverId)
    const m = savingRef.current
    if (!m.has(c.id)) {
      m.set(c.id, createChat(title, projectId)
        .then((saved) => { patchChat(c.id, (x) => ({ ...x, serverId: saved.id, loaded: true })); return saved.id })
        .catch(() => { m.delete(c.id); return undefined }))
    }
    return m.get(c.id)!
  }

  /** The result message the backend saved for this document. It's written just after the status changes,
   * so retry briefly. */
  async function savedOutcome(serverId: string, documentId: string): Promise<string | undefined> {
    for (let i = 0; i < 4; i++) {
      const saved = await getChat(serverId).catch(() => null)
      const m = saved?.messages.find((x) => x.documentId === documentId && (x.kind === 'result' || x.kind === 'error'))
      if (m) return m.text
      await sleep(1000)
    }
    return undefined
  }

  /** Upload to the backend, wait for the background workflow, then report the result in the chat and the panel. */
  async function submitToBackend(chatId: string, serverId: string | undefined, projectId: string, doc: ChatDoc) {
    const startedAt = Date.now()
    patchDoc(chatId, doc.id, { server: { projectId, phase: 'uploading', startedAt } })
    const finish = (phase: ServerResult['phase'], response: string, extra: Partial<ServerResult> = {}) => {
      patchServer(chatId, doc.id, { phase, response, finishedAt: Date.now(), ...extra })
      say(chatId, response, doc.id)
      setViewDoc(doc.id)
    }
    let uploaded: BackendDoc
    try {
      uploaded = await uploadDocument(projectId, doc.file!, serverId)
    } catch (e) { // rejected before a document existed, so the backend saved nothing about it
      const text = `Could not process ${doc.name}: ${e instanceof Error ? e.message : String(e)}`
      finish('error', text)
      if (serverId) postMessage(serverId, 'assistant', text, 'error').catch(() => {})
      return
    }
    try {
      patchServer(chatId, doc.id, { phase: 'processing', documentId: uploaded.id, doc: uploaded })
      say(chatId, `Uploaded ${doc.name}. Extracting text and running the rule checks. This can take a minute.`, doc.id)

      let current = uploaded
      for (let i = 0; i < 120 && current.status === 'processing'; i++) { // up to ~6 minutes
        await sleep(3000)
        current = (await listDocuments(projectId)).find((d) => d.id === uploaded.id) ?? current
      }

      const all = await refresh()
      // Prefer the message the backend saved, so this tab shows exactly what a reopened chat will show.
      const saved = serverId && current.status !== 'processing' ? await savedOutcome(serverId, uploaded.id) : undefined
      if (saved) {
        finish(current.status === 'error' ? 'error' : 'done', saved, { doc: current })
      } else if (current.status === 'error') {
        finish('error', `Processing ${doc.name} failed: ${current.error ?? 'unknown error'}`, { doc: current })
      } else if (current.status === 'processing') {
        finish('timeout', `${doc.name} is still processing. Check the Findings page in a few minutes.`, { doc: current })
      } else {
        const mine = all.filter((f) => f.documentId === uploaded.id)
        const open = mine.filter((f) => f.status !== 'passed')
        const count = (st: string) => mine.filter((f) => f.status === st).length
        finish('done',
          `Finished ${doc.name} (${current.pageCount} page${current.pageCount === 1 ? '' : 's'}, classified as ${current.docType.replace(/_/g, ' ')}). ` +
          `Checked ${mine.length} rule${mine.length === 1 ? '' : 's'}: ${count('failed')} failed, ${count('missing_evidence')} missing evidence, ` +
          `${count('needs_review')} need review, ${count('passed')} passed. ` +
          (open.length ? `The ${open.length} open issue${open.length === 1 ? ' is' : 's are'} waiting for a human reviewer. ` : '') +
          `Nothing is approved automatically.`,
          { doc: current })
      }
    } catch (e) {
      finish('error', `Could not process ${doc.name}: ${e instanceof Error ? e.message : String(e)}`)
    }
  }

  async function runOcr(chatId: string, doc: ChatDoc) {
    if (!doc.file) return
    if (!isPdf(doc.file)) { // DOCX/XLSX: no browser preview, the server extracts them
      patchDoc(chatId, doc.id, { status: 'done', progress: 1, method: 'server', pages: undefined,
        text: 'No browser preview for this file type. The server extracts and checks it.' })
      return
    }
    try {
      const res = await extractText(doc.file, (progress, label) => patchDoc(chatId, doc.id, { progress, label }))
      patchDoc(chatId, doc.id, { status: 'done', progress: 1, ...res })
    } catch (e) {
      patchDoc(chatId, doc.id, { status: 'error', error: e instanceof Error ? e.message : String(e) })
    }
  }

  async function send(text = input) {
    const trimmed = text.trim()
    if (!trimmed && !pending.length) return
    const chatId = chat.id
    const docs: ChatDoc[] = pending.map((p) => ({
      id: p.id, file: p.file, name: p.file.name, size: p.file.size, status: 'processing', progress: 0, label: 'Starting',
    }))
    const title = chat.title === 'New chat' ? trimmed.slice(0, 32) || docs[0]?.name || 'New chat' : chat.title
    patchChat(chatId, (c) => ({
      ...c,
      title,
      messages: [...c.messages, { id: uid(), role: 'user', text: trimmed, docIds: docs.map((d) => d.id) }],
      docs: [...c.docs, ...docs],
    }))
    setInput('')
    setPending([])
    docs.forEach((d) => runOcr(chatId, d)) // local preview only
    if (docs.length && uploadProjectId) setViewDoc(docs[0].id) // open the panel straight away so progress is visible

    const serverId = await ensureSaved(chat, title, uploadProjectId)
    if (serverId && trimmed) await postMessage(serverId, 'user', trimmed).catch(() => {}) // before the uploads, to keep the order

    if (!docs.length) {
      sayAndSave(chatId, serverId, 'Question answering is not built yet. Attach a PDF, DOCX or XLSX and I will run the rule checks on it.')
    } else if (!uploadProjectId) {
      sayAndSave(chatId, serverId, 'Create or select a project first (Projects page, or the project picker below), then attach the document again.')
    } else {
      docs.forEach((d) => submitToBackend(chatId, serverId, uploadProjectId, d))
    }
  }

  const shownDoc = viewDoc ? chat.docs.find((d) => d.id === viewDoc) : undefined

  return (
    <div
      className="chat-layout"
      onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
      onDragLeave={(e) => { if (e.currentTarget === e.target) setDragging(false) }}
      onDrop={(e) => { e.preventDefault(); setDragging(false); addFiles(e.dataTransfer.files) }}
    >
      <div className="chat-main">
        <div className="scroll">
          {chat.messages.length === 0 ? (
            <div className="empty">
              <div className="logo big">◎</div>
              <h1>Upload a fiber design or construction document</h1>
              <p>Drop a PDF, DOCX or XLSX. I'll extract it, check it against the rule library and send the findings to a human reviewer.</p>
              <div className="chips">
                {SUGGESTIONS.map((s) => <button key={s} className="chip" onClick={() => setInput(s)}>{s}</button>)}
              </div>
            </div>
          ) : (
            <div className="thread">
              {chat.messages.map((m) => (
                <div key={m.id} className={'msg ' + m.role}>
                  {m.role === 'assistant' && <div className="avatar">◎</div>}
                  <div className="bubble">
                    {m.docIds?.map((id) => {
                      const d = chat.docs.find((x) => x.id === id)
                      return d && <DocCard key={id} doc={d} onOpen={() => setViewDoc(d.id)} />
                    })}
                    {m.text && <p>{m.text}</p>}
                    {m.role === 'assistant' && (m.resultDocId || /waiting for a human reviewer/.test(m.text)) && (
                      <div className="msg-actions">
                        {m.resultDocId && <button className="chip" onClick={() => setViewDoc(m.resultDocId!)}>View details →</button>}
                        {/waiting for a human reviewer/.test(m.text) && (
                          <button className="chip" onClick={() => goTo('review')}>Open review queue →</button>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              ))}
              <div ref={endRef} />
            </div>
          )}
        </div>

        <div className="composer-wrap">
          <div className="project-pick">
            <label htmlFor="upload-project" className="muted">Check against project:</label>
            <select id="upload-project" value={uploadProjectId} onChange={(e) => setUploadProjectId(e.target.value)}>
              {projects.length === 0 && <option value="">No projects yet (create one on the Projects page)</option>}
              {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </div>
          <div className="composer">
            {pending.length > 0 && (
              <div className="attachments">
                {pending.map((p) => (
                  <span key={p.id} className="attach">
                    📄 {p.file.name}
                    <button onClick={() => setPending((ps) => ps.filter((x) => x.id !== p.id))} aria-label="Remove">×</button>
                  </span>
                ))}
              </div>
            )}
            <div className="row">
              <button className="icon-btn" title="Attach document" onClick={() => fileRef.current?.click()}>📎</button>
              <input ref={fileRef} type="file" hidden multiple accept=".pdf,.docx,.xlsx"
                onChange={(e) => { addFiles(e.target.files); e.target.value = '' }} />
              <textarea ref={taRef} rows={1} value={input} placeholder="Ask about your document…"
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }} />
              <button className="send" disabled={!input.trim() && !pending.length} onClick={() => send()} aria-label="Send">↑</button>
            </div>
          </div>
          <div className="disclaimer">AI findings must be confirmed by a human reviewer.</div>
        </div>
      </div>

      {shownDoc && (
        <ResultPanel key={shownDoc.id} doc={shownDoc} findings={findings} projects={projects}
          onReview={onReview} onClose={() => setViewDoc(null)} goTo={goTo} />
      )}

      {dragging && <div className="drop-overlay">Drop documents to upload</div>}
    </div>
  )
}

function Progress({ doc }: { doc: ChatDoc }) {
  return (
    <div className="progress">
      <div className="bar"><div style={{ width: `${Math.round(doc.progress * 100)}%` }} /></div>
      <span>{doc.label} · {Math.round(doc.progress * 100)}%</span>
    </div>
  )
}

const SERVER_LABEL: Record<ServerResult['phase'], string> = {
  uploading: 'uploading',
  processing: 'checking rules',
  done: 'checked',
  error: 'failed',
  timeout: 'still processing',
}

function DocCard({ doc, onOpen }: { doc: ChatDoc; onOpen: () => void }) {
  return (
    <button className="doccard" onClick={onOpen}>
      <span className="doc-icon">📄</span>
      <span className="doc-meta">
        <span className="doc-name">{doc.name}</span>
        <span className="muted">
          {doc.server ? `${fmtSize(doc.size)} · ${SERVER_LABEL[doc.server.phase]} · view details`
            : doc.status === 'processing' ? <Progress doc={doc} />
            : doc.status === 'done' ? `${fmtSize(doc.size)} · preview ready · view text`
            : 'Text preview failed'}
        </span>
      </span>
    </button>
  )
}
