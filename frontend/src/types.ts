export type Severity = 'high' | 'medium' | 'low'
export type Decision = 'pending' | 'approved' | 'rejected' | 'changes_requested'
/** 'rule' = deterministic Python check; 'ai' = LLM interpretation of unstructured evidence. */
export type FindingSource = 'rule' | 'ai'

export interface Comment {
  id: string
  author: string
  text: string
  at: string
}

export interface Finding {
  id: string
  projectId: string
  docName: string
  title: string
  severity: Severity
  source: FindingSource
  ruleId: string
  ruleText: string
  /** Quoted evidence from the document, or null when the required evidence is missing. */
  evidence: { page: number; quote: string } | null
  explanation: string
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
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  text: string
  docIds?: string[]
}

export interface Chat {
  id: string
  title: string
  messages: ChatMessage[]
  docs: ChatDoc[]
}
