import client from './client'
import type { StoredAuth } from '../types'

interface LoginData {
  access_token: string
  token_type: string
  expires_in: number
  must_change_password: boolean
  user: {
    id: number
    username: string
    display_name: string
    real_name: string
    role: 'super_admin' | 'dept_admin' | 'employee'
    dept_id: number | null
    dept_name: string | null
    dept_code: string | null
  }
}

export async function login(username: string, password: string): Promise<StoredAuth> {
  const { data } = await client.post<LoginData>('/auth/login', {
    username,
    password,
  })

  const { access_token, must_change_password, user } = data
  return {
    access_token,
    must_change_password,
    id:           user.id,
    username:     user.username,
    display_name: user.display_name,
    real_name:    user.real_name,
    role:         user.role,
    dept_id:      user.dept_id,
    dept_name:    user.dept_name,
    dept_code:    user.dept_code,
  }
}

export async function logout(): Promise<void> {
  try {
    await client.post('/auth/logout')
  } catch {
    // best-effort
  } finally {
    localStorage.removeItem('access_token')
    localStorage.removeItem('user_info')
  }
}
