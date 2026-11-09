import { useEffect, useRef, useState } from 'react'
import type { Dispatch, SetStateAction } from 'react'
import { extractText } from './ocr'
import { listDocuments, listFindings, uploadDocument } from './api'
import type { Chat, ChatDoc, Finding, Project } from './types'

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
}

export default function ChatView({ chats, setChats, activeId, projects, uploadProjectId, setUploadProjectId, refresh, goTo }: Props) {
  const [input, setInput] = useState('')
  const [pending, setPending] = useState<{ id: string; file: File }[]>([])
  const [viewDoc, setViewDoc] = useState<string | null>(null)
  const [dragging, setDragging] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)
  const endRef = useRef<HTMLDivElement>(null)
  const taRef = useRef<HTMLTextAreaElement>(null)

  const chat = chats.find((c) => c.id === activeId)!
  const patchChat = (id: string, fn: (c: Chat) => Chat) => setChats((cs) => cs.map((c) => (c.id === id ? fn(c) : c)))
  const patchDoc = (chatId: string, docId: string, patch: Partial<ChatDoc>) =>
    patchChat(chatId, (c) => ({ ...c, docs: c.docs.map((d) => (d.id === docId ? { ...d, ...patch } : d)) }))

  useEffect(() => { setViewDoc(null); setPending([]) }, [activeId])
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

  const say = (chatId: string, text: string) =>
    patchChat(chatId, (c) => ({ ...c, messages: [...c.messages, { id: uid(), role: 'assistant', text }] }))

  /** Upload to the backend, wait for the background workflow, then report the result in the chat. */
  async function submitToBackend(chatId: string, projectId: string, doc: ChatDoc) {
    try {
      const before = (await listFindings(projectId)).filter((f) => f.docName === doc.name).length
      const uploaded = await uploadDocument(projectId, doc.file)
      say(chatId, `Uploaded ${doc.name}. Extracting text and running the rule checks. This can take a minute.`)

      let current = uploaded
      for (let i = 0; i < 120 && current.status === 'processing'; i++) { // up to ~6 minutes
        await sleep(3000)
        current = (await listDocuments(projectId)).find((d) => d.id === uploaded.id) ?? current
      }

      const all = await refresh()
      if (current.status === 'error') {
        say(chatId, `Processing ${doc.name} failed: ${current.error ?? 'unknown error'}`)
      } else if (current.status === 'processing') {
        say(chatId, `${doc.name} is still processing. Check the Findings page in a few minutes.`)
      } else {
        const mine = all.filter((f) => f.projectId === projectId && f.docName === doc.name)
        const fresh = mine.slice(before)
        const n = (s: string) => fresh.filter((f) => f.severity === s).length
        say(chatId,
          `Finished ${doc.name} (${current.pageCount} page${current.pageCount === 1 ? '' : 's'}, classified as ${current.docType.replace('_', ' ')}).\n` +
          `${fresh.length} finding${fresh.length === 1 ? '' : 's'}: ${n('high')} high, ${n('medium')} medium, ${n('low')} low. ` +
          `They are waiting for a human reviewer. Nothing is approved automatically.`)
      }
    } catch (e) {
      say(chatId, `Could not process ${doc.name}: ${e instanceof Error ? e.message : String(e)}`)
    }
  }

  async function runOcr(chatId: string, doc: ChatDoc) {
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

  function send(text = input) {
    const trimmed = text.trim()
    if (!trimmed && !pending.length) return
    const chatId = chat.id
    const docs: ChatDoc[] = pending.map((p) => ({
      id: p.id, file: p.file, name: p.file.name, size: p.file.size, status: 'processing', progress: 0, label: 'Starting',
    }))
    patchChat(chatId, (c) => ({
      ...c,
      title: c.title === 'New chat' ? trimmed.slice(0, 32) || docs[0]?.name || 'New chat' : c.title,
      messages: [...c.messages, { id: uid(), role: 'user', text: trimmed, docIds: docs.map((d) => d.id) }],
      docs: [...c.docs, ...docs],
    }))
    setInput('')
    setPending([])
    docs.forEach((d) => runOcr(chatId, d)) // local preview only

    if (!docs.length) {
      say(chatId, 'Question answering is not built yet. Attach a PDF, DOCX or XLSX and I will run the rule checks on it.')
    } else if (!uploadProjectId) {
      say(chatId, 'Create or select a project first (Projects page, or the project picker below), then attach the document again.')
    } else {
      docs.forEach((d) => submitToBackend(chatId, uploadProjectId, d))
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
                    {m.role === 'assistant' && /waiting for a human reviewer/.test(m.text) && (
                      <button className="chip" onClick={() => goTo('review')}>Open review queue →</button>
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
        <aside className="docpanel">
          <div className="docpanel-head">
            <div>
              <strong>{shownDoc.name}</strong>
              <div className="muted">{shownDoc.status === 'done' ? `${shownDoc.pages} page(s) · ${shownDoc.method}` : shownDoc.status}</div>
            </div>
            <button className="icon-btn" onClick={() => setViewDoc(null)}>×</button>
          </div>
          <div className="docpanel-body">
            {shownDoc.status === 'processing' && <Progress doc={shownDoc} />}
            {shownDoc.status === 'error' && <p className="err">OCR failed: {shownDoc.error}</p>}
            {shownDoc.status === 'done' && <pre>{shownDoc.text || '(No text detected)'}</pre>}
          </div>
        </aside>
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

function DocCard({ doc, onOpen }: { doc: ChatDoc; onOpen: () => void }) {
  return (
    <button className="doccard" onClick={onOpen}>
      <span className="doc-icon">📄</span>
      <span className="doc-meta">
        <span className="doc-name">{doc.name}</span>
        <span className="muted">
          {doc.status === 'processing' && <Progress doc={doc} />}
          {doc.status === 'done' && `${fmtSize(doc.size)} · ${doc.method === 'server' ? 'sent to server' : 'preview ready · view text'}`}
          {doc.status === 'error' && 'OCR failed'}
        </span>
      </span>
    </button>
  )
}
