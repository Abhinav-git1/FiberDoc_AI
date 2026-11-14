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
  status: 'uploaded' | 'processing' | 'awaiting_review' | 'error'
  pageCount: number
  error: string | null
  sha256?: string | null
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
  file: File
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
}
