import type { StoredAuth } from '../types'

export function getStoredUser(): StoredAuth | null {
  try {
    const raw = localStorage.getItem('user_info')
    return raw ? (JSON.parse(raw) as StoredAuth) : null
  } catch {
    return null
  }
}

export function storeAuth(data: StoredAuth): void {
  localStorage.setItem('access_token', data.access_token)
  localStorage.setItem('user_info', JSON.stringify(data))
}

export function clearAuth(): void {
  localStorage.removeItem('access_token')
  localStorage.removeItem('user_info')
}

export function isLoggedIn(): boolean {
  return Boolean(localStorage.getItem('access_token'))
}
