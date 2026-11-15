/**
 * Rebuilds a chat as the UI shows it from what the backend saved (GET /api/chats/{id}).
 *
 * The backend stores one row per message, and one `upload` row per file. A user's text plus the files sent with it
 * are merged back into one bubble, as they looked when sent.
 */
import type { BackendDoc, Chat, ChatDoc, ChatMessage, SavedChat, SavedChatSummary, ServerResult } from './types'

const PHASE: Record<BackendDoc['status'], ServerResult['phase']> = {
  uploaded: 'processing',
  processing: 'processing',
  awaiting_review: 'done',
  error: 'error',
}

/** A chat in the sidebar whose messages haven't been fetched yet. */
export const stubChat = (s: SavedChatSummary): Chat =>
  ({ id: s.id, serverId: s.id, title: s.title, messages: [], docs: [], loaded: false })

export function fromSaved(s: SavedChat): Chat {
  const byDoc = new Map(s.documents.map((d) => [d.id, d]))
  const time = (iso: string) => new Date(iso).getTime()

  const docs: ChatDoc[] = s.documents.map((d) => {
    const upload = s.messages.find((m) => m.kind === 'upload' && m.documentId === d.id)
    const outcome = s.messages.find((m) => (m.kind === 'result' || m.kind === 'error') && m.documentId === d.id)
    return {
      id: d.id,
      name: d.name,
      size: d.sizeBytes ?? 0,
      status: 'done',
      progress: 1,
      label: '',
      server: {
        projectId: d.projectId,
        documentId: d.id,
        phase: PHASE[d.status],
        doc: d,
        startedAt: time(upload?.createdAt ?? d.createdAt ?? s.createdAt),
        finishedAt: outcome ? time(outcome.createdAt) : undefined,
        response: outcome?.text,
      },
    }
  })

  const messages: ChatMessage[] = []
  for (const m of s.messages) {
    const last = messages[messages.length - 1]
    if (m.kind === 'upload' && m.documentId) {
      if (!byDoc.has(m.documentId)) { // the document was deleted; keep a trace of it
        messages.push({ id: m.id, role: 'user', text: `📄 ${m.text} (document no longer available)` })
      } else if (last?.role === 'user') { // same send as the text or files just before it
        last.docIds = [...(last.docIds ?? []), m.documentId]
      } else {
        messages.push({ id: m.id, role: 'user', text: '', docIds: [m.documentId] })
      }
      continue
    }
    messages.push({
      id: m.id,
      role: m.role,
      text: m.text,
      resultDocId: m.role === 'assistant' && m.documentId && byDoc.has(m.documentId) ? m.documentId : undefined,
    })
  }

  return { id: s.id, serverId: s.id, title: s.title, messages, docs, loaded: true }
}

/** True while any document of the chat is still being checked on the server. */
export const stillProcessing = (c: Chat) => c.docs.some((d) => d.server?.phase === 'processing')
