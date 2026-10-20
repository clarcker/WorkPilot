/**
 * 管理后台 API（部门 / 用户 / 文档）
 */
import client from './client'

interface PagedData<T> { items: T[]; total: number; page: number; page_size: number }

// ── Departments ───────────────────────────────────────────────────

export interface Dept {
  id: number
  dept_code: string
  dept_name: string
  created_at: string
  user_count: number
}

export async function listDepts(): Promise<Dept[]> {
  const { data } = await client.get<Dept[]>('/admin/departments/')
  return data ?? []
}

export async function createDept(body: { dept_code: string; dept_name: string }): Promise<Dept> {
  const { data } = await client.post<Dept>('/admin/departments/', body)
  return data
}

export async function updateDept(id: number, dept_name: string): Promise<Dept> {
  const { data } = await client.patch<Dept>(`/admin/departments/${id}`, { dept_name })
  return data
}

export async function deleteDept(id: number): Promise<void> {
  await client.delete(`/admin/departments/${id}`)
}

// ── Users ─────────────────────────────────────────────────────────

export interface AdminUser {
  id: number
  username: string
  employee_no: string | null
  display_name: string
  real_name: string
  role: 'super_admin' | 'dept_admin' | 'employee'
  dept_id: number | null
  dept_name: string | null
  dept_code: string | null
  email: string | null
  is_active: boolean
  locked_at: string | null
  failed_login_count: number
  must_change_password: boolean
  last_login_at: string | null
  created_at: string
  notes: string | null
}

export interface UserCreateResult extends AdminUser {
  init_password: string
}

export interface CreateUserBody {
  username: string
  employee_no: string
  real_name: string
  role: 'dept_admin' | 'employee'
  dept_id: number | null
  email?: string
  notes?: string
}

export async function listUsers(params?: {
  page?: number
  page_size?: number
  dept_id?: number | null
  role?: string
  keyword?: string
}): Promise<{ items: AdminUser[]; total: number }> {
  const { data } = await client.get<PagedData<AdminUser>>('/admin/users/', { params })
  return { items: data?.items ?? [], total: data?.total ?? 0 }
}

export async function suggestUsername(name: string): Promise<string> {
  const { data } = await client.get<{ suggested: string }>(
    '/admin/users/suggest-username', { params: { name } }
  )
  return data.suggested
}

export async function suggestEmployeeNo(dept_id: number): Promise<string> {
  const { data } = await client.get<{ suggested: string }>(
    '/admin/users/suggest-employee-no', { params: { dept_id } }
  )
  return data.suggested
}

export async function createUser(body: CreateUserBody): Promise<UserCreateResult> {
  const { data } = await client.post<UserCreateResult>('/admin/users/', body)
  return data
}

export async function resetPassword(userId: number): Promise<string> {
  const { data } = await client.post<{ new_password: string }>(
    `/admin/users/${userId}/reset-password`
  )
  return data.new_password
}

export async function setUserStatus(userId: number, is_active: boolean): Promise<void> {
  await client.patch(`/admin/users/${userId}/status`, { is_active })
}

export async function unlockUser(userId: number): Promise<void> {
  await client.post(`/admin/users/${userId}/unlock`)
}

// ── Documents ─────────────────────────────────────────────────────

export interface AdminDoc {
  id: number
  file_uuid: string
  file_name: string
  file_size: number
  file_type: string
  dept_id: number | null
  dept_name: string | null
  visibility: string
  status: string          // processing | ready | failed | archived
  lifecycle?: string      // effective | superseded | draft
  effective_date?: string | null
  supersedes_doc_id?: number | null
  supersedes_name?: string | null
  superseded_by_name?: string | null
  error_message: string | null
  category: string | null
  version: string | null
  uploaded_by_name: string | null
  created_at: string
  updated_at: string
  chunk_count: number | null
}

export interface VersionChainItem {
  id: number
  file_name: string
  lifecycle: string
  effective_date: string | null
  status: string
  is_self: boolean
}

export async function listDocs(params?: {
  page?: number
  page_size?: number
  dept_id?: number | null
  lifecycle?: string | null
}): Promise<{ items: AdminDoc[]; total: number }> {
  const { data } = await client.get<PagedData<AdminDoc>>('/docs/', { params })
  return { items: data?.items ?? [], total: data?.total ?? 0 }
}

export async function uploadDoc(formData: FormData): Promise<AdminDoc> {
  const { data } = await client.post<AdminDoc>('/docs/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

export async function updateDoc(
  id: number,
  body: { lifecycle?: string; effective_date?: string; visibility?: string; category?: string; version?: string },
): Promise<AdminDoc> {
  const { data } = await client.patch<AdminDoc>(`/docs/${id}`, body)
  return data
}

export async function getDocVersionChain(id: number): Promise<VersionChainItem[]> {
  const { data } = await client.get<VersionChainItem[]>(`/docs/${id}/version-chain`)
  return Array.isArray(data) ? data : (data as unknown as { items?: VersionChainItem[] })?.items ?? []
}

export async function reindexDoc(id: number): Promise<void> {
  await client.post(`/docs/${id}/reindex`)
}

export async function archiveDoc(id: number): Promise<void> {
  await client.delete(`/docs/${id}`)
}

export async function getDocPermissions(id: number): Promise<number[]> {
  const { data } = await client.get<{ user_ids: number[] }>(`/docs/${id}/permissions`)
  return data?.user_ids ?? []
}

export async function setDocPermissions(id: number, user_ids: number[]): Promise<void> {
  await client.put(`/docs/${id}/permissions`, { user_ids })
}

// ── Audit Logs ────────────────────────────────────────────────────

export interface AuditLogItem {
  id: number
  operator_id: number | null
  operator_name: string
  action: string
  resource_type: string | null
  resource_id: string | null
  old_value: Record<string, unknown> | null
  new_value: Record<string, unknown> | null
  ip_address: string | null
  result: string
  detail: string | null
  created_at: string
}

export async function listAuditLogs(params?: {
  page?: number
  page_size?: number
  action?: string
  operator_name?: string
  result?: string
  start_time?: string
  end_time?: string
}): Promise<{ items: AuditLogItem[]; total: number }> {
  const { data } = await client.get<PagedData<AuditLogItem>>('/admin/audit/', { params })
  return { items: data?.items ?? [], total: data?.total ?? 0 }
}

// ── System Config ─────────────────────────────────────────────────

export interface SystemConfigItem {
  value: number
  label: string
  default: number
}

export type SystemConfigMap = Record<string, SystemConfigItem>

export async function getSystemConfig(): Promise<SystemConfigMap> {
  const { data } = await client.get<SystemConfigMap>('/admin/system/config')
  return data ?? {}
}

export async function updateSystemConfig(key: string, value: number): Promise<void> {
  await client.patch(`/admin/system/config/${key}`, { value })
}

// ── System Logs ─────────────────────────────────────────────────

export interface LogEntry {
  timestamp: string
  level: string
  location: string
  request_id: string
  user_id: string
  message: string
}

export interface LogResponse {
  date: string
  file_exists: boolean
  total: number
  page: number
  page_size: number
  items: LogEntry[]
}

export async function getSystemLogs(params?: {
  log_date?: string
  level?: string
  keyword?: string
  page?: number
  page_size?: number
}): Promise<LogResponse> {
  const { data } = await client.get<LogResponse>('/admin/system/logs', { params })
  return data ?? { date: '', file_exists: false, total: 0, page: 1, page_size: 100, items: [] }
}

// ── Reimbursement Approvals ──────────────────────────────────────

export interface ApprovalItem {
  id: number
  request_no: string
  user_id: number
  dept_id: number | null
  category: string
  amount: number
  days: number | null
  trip_start: string | null
  trip_end: string | null
  approval_ref: string | null
  precheck_result: {
    ok?: boolean
    remaining?: number
    daily_max?: number
    requires_special_approval?: boolean
    violations?: Array<{ rule?: string; message?: string; over_amount?: number }>
  } | null
  status: string
  created_at: string
}

export async function listApprovals(page = 1, pageSize = 20): Promise<{
  items: ApprovalItem[]
  total: number
}> {
  const { data } = await client.get<PagedData<ApprovalItem>>('/reimbursements/approvals', {
    params: { page, page_size: pageSize },
  })
  return { items: data?.items ?? [], total: data?.total ?? 0 }
}

export async function decideApproval(
  id: number,
  approved: boolean,
  comment?: string,
): Promise<{ request_no: string; status: string }> {
  const { data } = await client.post<{ request_no: string; status: string }>(
    `/reimbursements/${id}/decision`,
    { approved, comment },
  )
  return data
}

// ── Agent Traces ─────────────────────────────────────────────────

export interface AgentTraceStep {
  node: string
  output_summary?: string
  latency_ms?: number
  error?: string | null
}

export interface AgentTraceListItem {
  id: number
  conversation_id: number | null
  user_id: number
  query: string
  intent: string | null
  rewritten_query: string | null
  steps: AgentTraceStep[]
  tool_calls: Array<Record<string, unknown>> | null
  llm_model: string | null
  total_latency_ms: number | null
  error: string | null
  created_at: string
}

export interface AgentTraceDetail extends AgentTraceListItem {
  final_answer: string | null
  sources: Array<Record<string, unknown>> | null
}

export async function listTraces(params?: {
  page?: number
  page_size?: number
  user_id?: number
  conversation_id?: number
}): Promise<{ items: AgentTraceListItem[]; total: number }> {
  const { data } = await client.get<PagedData<AgentTraceListItem>>('/admin/traces/', {
    params,
  })
  return { items: data?.items ?? [], total: data?.total ?? 0 }
}

export async function getTrace(id: number): Promise<AgentTraceDetail> {
  const { data } = await client.get<AgentTraceDetail>(`/admin/traces/${id}`)
  return data
}

// ── IT Tickets (admin) ───────────────────────────────────────────

export interface AdminTicket {
  id: number
  ticket_no: string
  user_id: number
  user_name: string
  issue_type: string
  description: string
  status: string
  handle_note: string | null
  created_at: string
}

export async function listAdminTickets(
  page = 1,
  pageSize = 20,
  status?: string,
): Promise<{ items: AdminTicket[]; total: number }> {
  const { data } = await client.get<PagedData<AdminTicket>>('/admin/tickets/all', {
    params: { page, page_size: pageSize, status: status || undefined },
  })
  return { items: data?.items ?? [], total: data?.total ?? 0 }
}

export async function updateTicket(
  id: number,
  status: 'open' | 'in_progress' | 'closed',
  handle_note?: string,
): Promise<{ ticket_no: string; status: string }> {
  const { data } = await client.post<{ ticket_no: string; status: string }>(
    `/admin/tickets/${id}/decision`,
    { status, handle_note },
  )
  return data
}

// ── Q4 Eval management ──────────────────────────────────────────

export interface EvalCaseItem {
  id: number
  case_id: string
  question: string
  group: string | null
  payload: Record<string, unknown>
  source: string
  active: boolean
  created_at?: string | null
  last_run?: {
    run_id: number | null
    mode: string | null
    label: string | null
    result: Record<string, unknown> | null
  } | null
}

export interface EvalRunItem {
  id: number
  started_at?: string | null
  finished_at?: string | null
  total_cases: number
  scored_cases?: number
  timeout_count?: number
  intent_accuracy?: number | null
  doc_hit_rate?: number | null
  mrr?: number | null
  tool_call_accuracy?: number | null
  citation_rate?: number | null
  permission_pass_rate?: number | null
  avg_latency_ms?: number | null
  failed_cases?: unknown[] | null
  note?: string | null
  label?: string | null
  mode?: string | null
  status?: string | null
  progress?: number | null
  judge_model?: string | null
  faithfulness_avg?: number | null
  points_coverage?: number | null
  hallucination_count?: number | null
  refusal_correct_rate?: number | null
}

export interface EvalRunDetail extends EvalRunItem {
  case_results?: Array<Record<string, unknown>>
  judge_cases?: Array<{
    case_id: string
    question?: string
    group?: string
    answer_preview?: string
    judge?: {
      faithfulness?: number
      points_covered?: string
      hallucinated_claims?: string[]
      citation_correct?: boolean
      error?: string
    }
  }>
  metrics?: Record<string, number | null>
}

export interface EvalDiffResult {
  run_a: { id: number; label?: string | null; mode?: string | null }
  run_b: { id: number; label?: string | null; mode?: string | null }
  became_pass: Array<{ case_id: string; question?: string; group?: string; a_passed?: boolean; b_passed?: boolean }>
  became_fail: Array<{ case_id: string; question?: string; group?: string; a_passed?: boolean; b_passed?: boolean }>
  still_fail: Array<{ case_id: string; question?: string; group?: string; a_passed?: boolean; b_passed?: boolean }>
  by_group: Record<string, { became_pass: number; became_fail: number; still_fail: number }>
}

export async function listEvalCases(params?: {
  page?: number
  page_size?: number
  group?: string | null
  keyword?: string | null
}): Promise<{ items: EvalCaseItem[]; total: number }> {
  const { data } = await client.get<PagedData<EvalCaseItem>>('/quality/eval-cases', {
    params: {
      page: params?.page ?? 1,
      page_size: params?.page_size ?? 20,
      group: params?.group || undefined,
      keyword: params?.keyword || undefined,
    },
  })
  return { items: data?.items ?? [], total: data?.total ?? 0 }
}

export async function listEvalCaseGroups(): Promise<string[]> {
  const { data } = await client.get<string[]>('/quality/eval-cases/groups')
  return data ?? []
}

export async function getEvalCase(caseId: string): Promise<EvalCaseItem> {
  const { data } = await client.get<EvalCaseItem>(`/quality/eval-cases/${caseId}`)
  return data
}

export async function createEvalCase(body: {
  case_id?: string
  question: string
  group?: string | null
  payload: Record<string, unknown>
  active?: boolean
}): Promise<EvalCaseItem> {
  const { data } = await client.post<EvalCaseItem>('/quality/eval-cases', body)
  return data
}

export async function updateEvalCase(
  caseId: string,
  body: {
    question?: string
    group?: string | null
    payload?: Record<string, unknown>
    active?: boolean
  },
): Promise<EvalCaseItem> {
  const { data } = await client.patch<EvalCaseItem>(`/quality/eval-cases/${caseId}`, body)
  return data
}

export async function seedEvalCases(): Promise<{ imported: number }> {
  const { data } = await client.post<{ imported: number }>('/quality/cases/seed')
  return data ?? { imported: 0 }
}

export interface EvalTriggerResult {
  run_id?: number
  mode?: string
  status?: string
  total_estimate?: number
  total_cases?: number
  scored_cases?: number
  doc_hit_rate?: number
  mrr?: number
  faithfulness_avg?: number
  points_coverage?: number
  hallucination_count?: number
  label?: string
  note?: string
  case_results?: Array<Record<string, unknown>>
  failed_cases?: Array<Record<string, unknown>>
  by_group?: Record<string, unknown>
}

export async function triggerEvalRun(params?: {
  mode?: 'fast' | 'judge'
  label?: string
  skip_generation?: boolean
  tool_dry_run?: boolean
  concurrency?: number
}): Promise<EvalTriggerResult> {
  const q = new URLSearchParams()
  q.set('mode', params?.mode || 'fast')
  if (params?.label) q.set('label', params.label)
  if (params?.skip_generation != null) q.set('skip_generation', String(params.skip_generation))
  if (params?.tool_dry_run != null) q.set('tool_dry_run', String(params.tool_dry_run))
  if (params?.concurrency) q.set('concurrency', String(params.concurrency))
  const { data } = await client.post<EvalTriggerResult>(`/eval/run?${q.toString()}`)
  return data ?? {}
}

export async function listEvalRuns(): Promise<EvalRunItem[]> {
  const { data } = await client.get<EvalRunItem[]>('/quality/runs')
  return data ?? []
}

export async function getEvalRun(id: number): Promise<EvalRunDetail> {
  const { data } = await client.get<EvalRunDetail>(`/quality/runs/${id}`)
  return data
}

export async function diffEvalRuns(runId: number, otherId: number): Promise<EvalDiffResult> {
  const { data } = await client.get<EvalDiffResult>(`/quality/runs/${runId}/diff`, {
    params: { other_id: otherId },
  })
  return data
}

// ── P9 Notifications ─────────────────────────────────────────────

export interface NotificationItem {
  id: number
  title: string
  body: string
  level: string
  source: string
  payload?: Record<string, unknown> | null
  is_read: boolean
  created_at?: string | null
}

export async function listNotifications(params?: {
  page?: number
  page_size?: number
  unread_only?: boolean
}): Promise<{ items: NotificationItem[]; total: number }> {
  const { data } = await client.get<PagedData<NotificationItem>>('/admin/notifications', {
    params: {
      page: params?.page ?? 1,
      page_size: params?.page_size ?? 20,
      unread_only: params?.unread_only || undefined,
    },
  })
  return { items: data?.items ?? [], total: data?.total ?? 0 }
}

export async function unreadNotificationCount(): Promise<number> {
  const { data } = await client.get<{ count: number }>('/admin/notifications/unread-count')
  return data?.count ?? 0
}

export async function markNotificationRead(id: number): Promise<void> {
  await client.post(`/admin/notifications/${id}/read`)
}

export async function markAllNotificationsRead(): Promise<void> {
  await client.post('/admin/notifications/read-all')
}
