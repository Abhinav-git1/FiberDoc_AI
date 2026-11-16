/**
 * API layer: talks to the FastAPI backend.
 *   listProjects   -> GET  /api/projects
 *   createProject  -> POST /api/projects
 *   listDocuments  -> GET  /api/projects/{id}/documents
 *   uploadDocument -> POST /api/projects/{id}/documents   (multipart; processed in the background)
 *   listFindings   -> GET  /api/findings
 *   reviewFinding  -> POST /api/findings/{id}/review
 *   listChats      -> GET  /api/chats
 *   createChat     -> POST /api/chats
 *   getChat        -> GET  /api/chats/{id}         (messages + the documents they refer to)
 *   postMessage    -> POST /api/chats/{id}/messages
 *   getTimings     -> GET  /api/documents/{id}/timings  (where the processing time went)
 *
 * The backend returns camelCase JSON that already matches ./types, so no mapping is needed.
 * The base URL comes from VITE_API_URL (see frontend/.env).
 */
import type { BackendDoc, Decision, Finding, Project, SavedChat, SavedChatSummary, SavedMessage, Timings } from './types'

const BASE = (import.meta.env.VITE_API_URL ?? 'http://localhost:8000').replace(/\/$/, '')

/** FastAPI error bodies look like {"detail": "..."} or {"detail": [{"msg": ...}]}; show something readable. */
async function errorMessage(res: Response): Promise<string> {
  const raw = await res.text().catch(() => '')
  try {
    const detail = JSON.parse(raw).detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) return detail.map((d) => d.msg).join('; ')
  } catch { /* not JSON */ }
  return raw || res.statusText
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  // For FormData the browser must set the multipart Content-Type (with its boundary) itself.
  const headers = typeof init.body === 'string' ? { 'Content-Type': 'application/json' } : undefined
  let res: Response
  try {
    res = await fetch(`${BASE}${path}`, { ...init, headers })
  } catch {
    throw new Error(`Cannot reach the backend at ${BASE}. Is it running?`)
  }
  if (!res.ok) throw new Error(await errorMessage(res))
  return res.json() as Promise<T>
}

export const listProjects = () => request<Project[]>('/api/projects')

export const createProject = (name: string, location: string) =>
  request<Project>('/api/projects', { method: 'POST', body: JSON.stringify({ name, location }) })

export const listDocuments = (projectId: string) =>
  request<BackendDoc[]>(`/api/projects/${encodeURIComponent(projectId)}/documents`)

/** With chatId, the backend saves the upload and (when checking ends) the result message in that chat. */
export function uploadDocument(projectId: string, file: File, chatId?: string) {
  const form = new FormData()
  form.append('file', file)
  if (chatId) form.append('chat_id', chatId)
  return request<BackendDoc>(`/api/projects/${encodeURIComponent(projectId)}/documents`, { method: 'POST', body: form })
}

/** Direct link: the backend answers with Content-Disposition: attachment, so the browser downloads it. */
export const reportUrl = (projectId: string) => `${BASE}/api/projects/${encodeURIComponent(projectId)}/report`

export const listFindings = (projectId?: string) =>
  request<Finding[]>(`/api/findings${projectId ? `?project_id=${encodeURIComponent(projectId)}` : ''}`)

export const reviewFinding = (id: string, decision: Decision, comment: string) =>
  request<Finding>(`/api/findings/${encodeURIComponent(id)}/review`, {
    method: 'POST',
    body: JSON.stringify({ decision, comment }),
  })

export const listChats = () => request<SavedChatSummary[]>('/api/chats')

export const createChat = (title: string, projectId?: string) =>
  request<SavedChatSummary>('/api/chats', { method: 'POST', body: JSON.stringify({ title, projectId: projectId || null }) })

export const getChat = (id: string) => request<SavedChat>(`/api/chats/${encodeURIComponent(id)}`)

export const getTimings = (documentId: string) => request<Timings>(`/api/documents/${encodeURIComponent(documentId)}/timings`)

/** Only 'text' and 'error' messages can be posted; upload and result messages come from the backend. */
export const postMessage = (chatId: string, role: 'user' | 'assistant', text: string, kind: 'text' | 'error' = 'text') =>
  request<SavedMessage>(`/api/chats/${encodeURIComponent(chatId)}/messages`, {
    method: 'POST',
    body: JSON.stringify({ role, text, kind }),
  })
