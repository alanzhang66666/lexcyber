export type StubResult = {
  summary?: string
  status?: string
  review_status?: string
  human_approval_required?: boolean
  metadata_keys?: unknown
  runner?: string
}

export function asStubResult(content: unknown): StubResult | null {
  if (!content || typeof content !== 'object' || Array.isArray(content)) return null
  const record = content as Record<string, unknown>
  if (!('summary' in record || 'runner' in record || 'human_approval_required' in record)) return null
  return {
    summary: typeof record.summary === 'string' ? record.summary : undefined,
    status: typeof record.status === 'string' ? record.status : undefined,
    review_status: typeof record.review_status === 'string' ? record.review_status : undefined,
    human_approval_required: typeof record.human_approval_required === 'boolean' ? record.human_approval_required : undefined,
    metadata_keys: record.metadata_keys,
    runner: typeof record.runner === 'string' ? record.runner : undefined,
  }
}

export function renderRawContent(content: unknown) {
  if (content === null || content === undefined || content === '') return ''
  return typeof content === 'string' ? content : JSON.stringify(content, null, 2)
}

export const TASK_STATUS_STAGE: Record<string, string> = {
  queued: '排队',
  running: '执行',
  waiting_review: '待复核',
  completed: '已完成',
  failed: '失败',
  timed_out: '超时',
  rejected: '已拒绝',
}
