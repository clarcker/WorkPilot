import client from './client'

export interface ReimbSummary {
  id: number
  request_no: string
  category: string
  amount: number
  status: string
  created_at?: string
  approver_comment?: string | null
}

export interface ConfirmResult {
  request_no: string
  status: string
  message?: string
}

export async function confirmReimbursement(requestId: number): Promise<ConfirmResult> {
  const { data } = await client.post<ConfirmResult>(`/reimbursements/${requestId}/confirm`)
  return data
}

export async function cancelReimbursement(requestId: number): Promise<ConfirmResult> {
  const { data } = await client.post<ConfirmResult>(`/reimbursements/${requestId}/cancel`)
  return data
}

export async function listMyReimbursements(status?: string): Promise<ReimbSummary[]> {
  const { data } = await client.get<ReimbSummary[]>('/reimbursements/mine', {
    params: status ? { status } : undefined,
  })
  return data
}
