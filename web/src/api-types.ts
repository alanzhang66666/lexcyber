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

export type TaskType =
  | 'document.parse'
  | 'model.probe'
  | 'sentencing.calculate'
  | 'compliance.analyze'
  | 'conviction.analyze'

export type VerificationStatus =
  | 'candidate'
  | 'baseline_asserted'
  | 'confirmed'
  | 'rejected'
  | 'conflicted'

export type ModuleApplicability = 'unknown' | 'not_applicable' | 'limited_context' | 'applicable'
export type ModuleName = 'compliance' | 'conviction'
export type ArchiveStatus = 'open' | 'archived'

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
  caseId?: string | null
  module?: string | null
  resultVersion: number
  status: ReviewStatus
  decision: ReviewDecisionValue
  actor?: string | null
  comment?: string | null
  authenticated?: boolean | null
  decidedAt?: string | null
  draftId?: string | null
  draftVersion?: number | null
  moduleState?: ModuleName | null
  moduleVersion?: number | null
  archiveStatus?: ArchiveStatus | null
  returnTarget?: string | null
}

export type ReviewOpen = {
  module: string
  draftId?: string | null
  draftVersion?: number | null
  moduleState?: ModuleName | null
  moduleVersion?: number | null
  resultVersion?: number | null
  taskId?: string | null
  returnTarget?: string | null
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

export type CaseEventDocumentUpdate = {
  documentId: string
  locator?: string
}

/** 案件 metadata.relations 里的客观关系结构（T1 API-01 约定，不含法律定性） */
export type RelationActor = {
  actorId: string
  label?: string
  roleHint?: string
}

export type RelationOrganization = {
  organizationId: string
  label?: string
  actorId?: string
}

export type RelationAccount = {
  accountId: string
  organizationId?: string
  actorId?: string
  mask?: string
}

export type RelationEvent = {
  eventId: string
  stage?: string
  actorId?: string
  accountId?: string
  documentId?: string
  locator?: string
  occurredOn?: string
}

export type CaseRelations = {
  actors?: RelationActor[]
  organizations?: RelationOrganization[]
  accounts?: RelationAccount[]
  events?: RelationEvent[]
  links?: unknown[]
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
  verificationStatus?: VerificationStatus | null
  sourceVersion?: string | null
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

export type DraftCreate = {
  draftType: string
  body?: string | null
  templateVersion?: string | null
  sourceVersion?: string | null
}

export type DraftUpdate = {
  body: string
  version: number
  templateVersion?: string | null
  sourceVersion?: string | null
}

export type DraftView = {
  id: string
  caseId: string
  draftType: string
  body: string
  version: number
  updatedBy?: string | null
  updatedAt: string
  templateVersion?: string | null
  sourceVersion?: string | null
}

export type ModuleStateUpdate = {
  applicability?: ModuleApplicability | null
  content: Record<string, unknown>
  sourceVersion?: string | null
  version: number
}

export type ModuleStateView = {
  caseId: string
  module: ModuleName
  schemaVersion: 'case.module.v1'
  applicability: ModuleApplicability
  status: 'draft' | 'confirmed'
  version: number
  content: Record<string, unknown>
  sourceVersion?: string | null
  factsUpdatedAt?: string | null
  factsStale: boolean
  updatedBy?: string | null
  updatedAt: string
  confirmedAt?: string | null
}

export type DraftList = {
  items: DraftView[]
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

/* ── T3 分析结果展示类型（T2 内部契约；字段语义见 docx / t3-three-case-handoff）── */

/** 金额口径（八类 + 未分类）。页面必须区分标签，禁止把账户总流水冒充犯罪所得。 */
export type AmountKind =
  | 'account_total_flow'
  | 'fraud_related_inflow'
  | 'payment_settlement'
  | 'crime_amount'
  | 'crime_proceeds'
  | 'personal_participation'
  | 'personal_profit'
  | 'restitution'
  | 'unclassified_amount'

export type EvidenceRef = {
  id?: string | null
  quote?: string | null
  locator?: string | null
  documentId?: string | null
}

/** T3 事实卡条目：行为阶段 + 事实内容 + 待核状态 + 原文定位。 */
export type AnalysisFact = {
  id?: string | null
  /** 行为阶段（犯罪链中的时间/阶段） */
  stage?: string | null
  statement: string
  locator?: string | null
  sourceDocumentId?: string | null
  status?: VerificationStatus | null
}

export type CandidatePathKind = 'candidate' | 'alternative' | 'excluded'

/** 候选路径：支持证据与相反证据必须并列展示，不得只显示支持一方。 */
export type CandidatePath = {
  id?: string | null
  title: string
  kind?: CandidatePathKind | null
  summary?: string | null
  supporting?: EvidenceRef[]
  contrary?: EvidenceRef[]
  status?: VerificationStatus | null
}

/** 合规事实清单项（C 案）：T3 `analyses.compliance.checklist[]` 的维度 + 客观状态 + 证据，不做合规等级→罪责映射。 */
export type ComplianceChecklistItem = {
  category?: string | null
  status?: string | null
  evidenceIds?: string[]
}

/** 管辖连接点：T3 `jurisdiction_connections[]` 投影，原样展示类型/值/核验状态。 */
export type JurisdictionConnection = {
  connectionId?: string | null
  type?: string | null
  value?: string | null
  /** 允许域外专用状态（如 `not_required_for_cn_criminal_jurisdiction`），不限于五值核验枚举。 */
  status?: string | null
  evidenceIds?: string[]
}

/** 缺失事实/待确认项：T3 `missing_items[]` 投影，原样展示，不推断结论。 */
export type MissingItem = {
  id?: string | null
  severity?: string | null
  description?: string | null
}

/** 单条金额口径：标签 + 数值 + 币种 + 证据定位 + 确认状态。 */
export type AmountEntry = {
  kind: AmountKind
  label?: string | null
  value?: number | null
  currency?: string | null
  locator?: string | null
  evidenceIds?: string[]
  status?: VerificationStatus | null
}

/** 量刑 blocked 时的阻断项，展示待确认，不展示空结果。 */
export type Blocker = {
  code?: string | null
  path?: string | null
  message?: string | null
}

/* ── 量刑结果（T2 内部契约；blocked 时只展示阻断项，不展示刑期）── */

export type SentencingParameter = {
  name?: string | null
  value?: string | null
}

export type SentencingStep = {
  label?: string | null
  detail?: string | null
  value?: string | null
}

export type SentencingResult = {
  ruleVersion?: string | null
  parameters?: SentencingParameter[]
  steps?: SentencingStep[]
  interval?: string | null
  missing?: string[]
  amounts?: AmountEntry[]
  blockers?: Blocker[]
}

/* ── 协作导入（case-import.v1；独立于案件工作链路）── */

export type ImportBatchStatus =
  | 'uploading'
  | 'uploaded'
  | 'validating'
  | 'validation_failed'
  | 'diff_ready'
  | 'review_required'
  | 'approved'
  | 'applying'
  | 'partially_completed'
  | 'completed'
  | 'failed'

export type ImportStepStatus = 'pending' | 'running' | 'completed' | 'failed' | 'skipped'

export type ImportItemStatus =
  | 'pending'
  | 'validating'
  | 'invalid'
  | 'diff_ready'
  | 'review_required'
  | 'approved'
  | 'applying'
  | 'applied'
  | 'no_op'
  | 'conflict'
  | 'failed'

export type ImportStep = {
  stepKey: string
  attempt: number
  status: ImportStepStatus
  error?: Record<string, unknown> | null
  startedAt?: string | null
  finishedAt?: string | null
}

export type ImportBatch = {
  id: string
  status: ImportBatchStatus
  originalFilename: string
  contentType: string
  sizeBytes: number
  rawSha256: string
  createdAt: string
  updatedAt: string
  schemaVersion?: string | null
  packageId?: string | null
  producerId?: string | null
  datasetId?: string | null
  revision?: string | null
  packageDigest?: string | null
  error?: Record<string, unknown> | null
  approvedAt?: string | null
  startedAt?: string | null
  completedAt?: string | null
}

export type ImportItem = {
  id: string
  ordinal: number
  itemId: string
  externalCaseId: string
  status: ImportItemStatus
  payloadPath: string
  payloadSha256: string
  steps: ImportStep[]
  createdAt: string
  updatedAt: string
  caseId?: string | null
  diff?: { action?: 'create' | 'no_op' | 'conflict'; [key: string]: unknown } | null
  error?: Record<string, unknown> | null
  completedAt?: string | null
}

export type PageImportBatch = {
  items: ImportBatch[]
  page: number
  size: number
  total: number
}

export type PageImportItem = {
  items: ImportItem[]
  page: number
  size: number
  total: number
}
