/**
 * Generated contract snapshot for contracts/public-api.yaml.
 * Keep this file in sync when the public OpenAPI contract changes; CI validates
 * the source contract and the console build catches incompatible consumers.
 */
export type TaskStatus = 'queued' | 'running' | 'completed' | 'waiting_review' | 'failed' | 'timed_out' | 'rejected'

export type ResultRef = {
  resultId: string
  version: number
  type: string
  contentHash?: string | null
}

export type TaskView = {
  id: string
  requestId: string
  executionId: string
  status: TaskStatus
  currentStage: string
  result?: ResultRef | null
  errorCode?: string | null
  error?: string | null
  createdAt: string
  updatedAt: string
}

export type ReviewRecord = {
  id: string
  taskId: string
  resultVersion: number
  status: string
  decision: string
  comment?: string | null
}

export type ReviewPage = { items: ReviewRecord[]; page: number; size: number; total: number }

export type ResultPayload = {
  resultId: string
  version: number
  type: string
  contentHash: string
  content: unknown
}
