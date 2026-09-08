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
  status: string          // pending | processing | ready | failed
  error_message: string | null
  category: string | null
  version: string | null
  uploaded_by_name: string | null
  created_at: string
  updated_at: string
  chunk_count: number | null
}

export async function listDocs(params?: {
  page?: number
  page_size?: number
  dept_id?: number | null
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
