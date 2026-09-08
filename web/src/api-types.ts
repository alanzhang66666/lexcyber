/**
 * TypeScript snapshot of contracts/public-api.yaml.
 * Keep field names and enum values aligned with the public contract.
 */
export type TaskStatus =
  | 'queued'
  | 'running'
  | 'completed'
  | 'waiting_review'
  | 'failed'
  | 'timed_out'
  | 'rejected'

export type ReviewStatus = 'pending' | 'approved' | 'rejected' | 'superseded'
export type ReviewDecisionValue = 'approve' | 'reject' | 'retry' | 'none'

export type TaskType = 'document.parse' | 'model.probe' | 'sentencing.calculate'

export type TaskCreate = {
  query: string
  caseId?: string
  sessionId?: string
  metadata?: {
    taskType?: TaskType
    [key: string]: unknown
  }
}

export type SourceRef = {
  sourceId: string
  locator: string
  jurisdiction?: string
  version?: string
  effectiveFrom?: string
  effectiveTo?: string
}

export type ResultRef = {
  resultId: string
  version: number
  type: string
  contentHash?: string | null
  sourceRefs?: SourceRef[]
}

export type TaskView = {
  id: string
  requestId: string
  executionId: string
  caseId?: string | null
  status: TaskStatus
  currentStage?: string | null
  result?: ResultRef | null
  errorCode?: string | null
  error?: string | null
  createdAt: string
  updatedAt?: string | null
}

export type ReviewRecord = {
  id: string
  taskId?: string | null
  resultVersion: number
  status: ReviewStatus
  decision: ReviewDecisionValue
  actor?: string | null
  comment?: string | null
  authenticated?: boolean | null
  decidedAt?: string | null
}

export type ReviewPage = {
  items: ReviewRecord[]
  page: number
  size: number
  total: number
}

export type DocumentRole = 'input' | 'annotation'

export type ParseStatus =
  | 'not_started'
  | TaskStatus

export type CaseCreate = {
  title: string
  jurisdiction?: string | null
  asOfDate?: string | null
  metadata?: Record<string, unknown>
}

export type CaseView = {
  id: string
  title: string
  jurisdiction?: string | null
  asOfDate?: string | null
  metadata?: Record<string, unknown> | null
  createdAt: string
  updatedAt: string
}

export type PageCase = {
  items: CaseView[]
  page: number
  size: number
  total: number
}

export type DocumentView = {
  id: string
  caseId: string
  filename: string
  contentType: string
  size: number
  role: DocumentRole
  parseStatus: ParseStatus
  parseTaskId?: string | null
  createdAt: string
}

export type PageDocument = {
  items: DocumentView[]
  page: number
  size: number
  total: number
}

export type ReviewDecision = {
  resultVersion: number
  comment?: string
}

export type ResultPayload = {
  resultId: string
  version: number
  type: string
  contentHash: string
  content: unknown
}

export type AuthRegister = {
  username: string
  password: string
  displayName?: string
}

export type AuthLogin = {
  username: string
  password: string
}

export type SessionView = {
  token?: string | null
  username: string
  displayName: string
  expiresAt?: string | null
}

export type FactItem = {
  id?: string
  key: string
  value: string
  locator?: string | null
  sourceDocumentId?: string | null
}

export type FactUpdate = {
  items: FactItem[]
}

export type FactView = {
  caseId: string
  schemaVersion: 'case.facts.v1'
  status: 'draft' | 'confirmed'
  items: FactItem[]
  updatedAt: string
  confirmedAt?: string | null
}

export type SourceSearchRequest = {
  query: string
  jurisdiction?: string | null
  asOfDate?: string | null
  topK?: number
}

export type SourceSearchHit = {
  sourceId: string
  locator: string
  title?: string | null
  quote?: string | null
  version?: string | null
  jurisdiction?: string | null
}

export type SourceSearchResponse = {
  items: SourceSearchHit[]
}

export type ApiErrorPayload = {
  code?: string
  message?: string
  detail?: string
  traceId?: string
  retryable?: boolean
}
