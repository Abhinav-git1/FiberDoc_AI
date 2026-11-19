export type Severity = 'high' | 'medium' | 'low'
export type Decision = 'pending' | 'approved' | 'rejected' | 'changes_requested'
/** 'rule' = deterministic Python check; 'ai' = LLM interpretation of unstructured evidence. */
export type FindingSource = 'rule' | 'ai'
/** Result of the automatic check, separate from the human decision. */
export type FindingStatus = 'passed' | 'failed' | 'missing_evidence' | 'needs_review'

export interface Evidence {
  page: number
  quote: string
}

/** Why a rule was applied: the rule exactly as used, how it ranked, and (semantic rules) what the LLM was shown. */
export interface RetrievalTrace {
  rule: { id: string; version: string | null; source_name: string | null; section: string | null; check_type: string; text: string }
  doc_type: string
  ranking: { rank: number; score: number; vector: number; keyword: number } | null
  evidence_method?: 'vector' | 'keyword'
  evidence_chunks?: { chunk_id: string; page: number; similarity: number | null; excerpt: string }[]
}

export interface Comment {
  id: string
  author: string
  text: string
  at: string
}

export interface Finding {
  id: string
  projectId: string
  documentId: string
  docName: string
  title: string
  severity: Severity
  source: FindingSource
  ruleId: string
  ruleText: string
  /** Catalogue section of the rule ("Construction", "Permits", ...); null for rules without one. */
  ruleSection: string | null
  /** Quoted evidence from the document, or null when the required evidence is missing. */
  evidence: Evidence | null
  /** All evidence quotes (a consistency check has two). */
  evidenceList: Evidence[]
  explanation: string
  /** The fields below are null on findings created before they existed. */
  status: FindingStatus | null
  sourcePagesChecked: number[] | null
  recommendedAction: string | null
  needsHumanReview: boolean | null
  retrieval: RetrievalTrace | null
  decision: Decision
  comments: Comment[]
}

export interface Project {
  id: string
  name: string
  location: string
  docCount: number
}

/** A document record as returned by the backend (processing -> awaiting_review | error). */
export interface BackendDoc {
  id: string
  projectId: string
  name: string
  docType: string
  /** How sure the classifier was, 0-1, and why. Null for documents classified before 19 Nov 2026. */
  docTypeConfidence?: number | null
  docTypeReason?: string | null
  status: 'uploaded' | 'processing' | 'awaiting_review' | 'error'
  pageCount: number
  error: string | null
  sha256?: string | null
  /** Size of the stored original in bytes (null if the file is gone). */
  sizeBytes?: number | null
  createdAt?: string | null
}

/** Saved chats (backend tables chats / chat_messages). */
export interface SavedChatSummary {
  id: string
  title: string
  projectId: string | null
  createdAt: string
  updatedAt: string
}

export interface SavedMessage {
  id: string
  role: 'user' | 'assistant'
  text: string
  /** upload and result messages are written by the backend. */
  kind: 'text' | 'upload' | 'result' | 'error'
  documentId: string | null
  createdAt: string
}

export interface SavedChat extends SavedChatSummary {
  messages: SavedMessage[]
  documents: BackendDoc[]
}

/** What the backend did with a document uploaded from the chat (shown in the result panel). */
export interface ServerResult {
  projectId: string
  documentId?: string
  phase: 'uploading' | 'processing' | 'done' | 'error' | 'timeout'
  doc?: BackendDoc
  startedAt: number
  finishedAt?: number
  /** The assistant's reply about this document. */
  response?: string
}

export interface ChatDoc {
  id: string
  /** Missing for documents of a chat reopened from the server: the file stays on the server. */
  file?: File
  name: string
  size: number
  status: 'processing' | 'done' | 'error'
  progress: number
  label: string
  text?: string
  pages?: number
  method?: string
  error?: string
  server?: ServerResult
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  text: string
  docIds?: string[]
  /** Assistant replies about one document link to its result panel. */
  resultDocId?: string
}

export interface Chat {
  id: string
  title: string
  messages: ChatMessage[]
  docs: ChatDoc[]
  /** Set once the chat is saved on the server (on its first message). */
  serverId?: string
  /** false = only the title is loaded so far; the messages are fetched when the chat is opened. */
  loaded?: boolean
}

/** Where one document's processing time went (GET /api/documents/{id}/timings). */
export interface LlmCall {
  /** e.g. "embed 8 texts", "generate EvidenceCheck" */
  op: string
  /** Including retries and back-off. */
  seconds: number
  attempts: number
  errors: string[]
  failed: boolean
  /** The model that answered (or was tried last). Null for calls recorded before 19 Nov 2026. */
  model: string | null
  inputTokens: number | null
  outputTokens: number | null
  thinkingTokens: number | null
}

export interface Timings {
  totalS: number
  /** parse, embed_chunks, then the workflow nodes in order. */
  steps: { name: string; seconds: number }[]
  llmCalls: LlmCall[]
}

/** Outbound webhook settings (Automations page): a summary of each checked document goes to n8n, which emails it. */
export interface AutomationSettings {
  enabled: boolean
  webhookUrl: string | null
  recipientEmail: string | null
  /** Sent as the X-FiberDoc-Token header; n8n's Header Auth checks it. */
  secret: string
  updatedAt: string
}

export interface Delivery {
  id: string
  documentId: string | null
  documentName: string | null
  event: 'document.checked' | 'test'
  url: string
  status: 'sent' | 'failed'
  httpStatus: number | null
  attempts: number
  error: string | null
  createdAt: string
}
