import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { ConfigProvider, App as AntApp } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import Login from './pages/Login'
import Chat from './pages/Chat'
import ChangePassword from './pages/ChangePassword'
import Admin from './pages/Admin'
import { isLoggedIn, getStoredUser } from './hooks/useAuth'

function RequireAuth({ children }: { children: React.ReactNode }) {
  if (!isLoggedIn()) return <Navigate to="/login" replace />
  // Intercept must_change_password users before they reach any business page
  const user = getStoredUser()
  if (user?.must_change_password) return <Navigate to="/change-password" replace />
  return <>{children}</>
}

function RequireAdmin({ children }: { children: React.ReactNode }) {
  if (!isLoggedIn()) return <Navigate to="/login" replace />
  const user = getStoredUser()
  if (user?.must_change_password) return <Navigate to="/change-password" replace />
  if (user?.role !== 'super_admin' && user?.role !== 'dept_admin') {
    return <Navigate to="/" replace />
  }
  return <>{children}</>
}

export default function App() {
  return (
    <ConfigProvider
      locale={zhCN}
      theme={{
        token: {
          colorPrimary: '#1677ff',
          borderRadius: 8,
          fontFamily:
            '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif',
        },
      }}
    >
      <AntApp>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/change-password" element={<ChangePassword />} />
            <Route
              path="/admin/*"
              element={
                <RequireAdmin>
                  <Admin />
                </RequireAdmin>
              }
            />
            <Route
              path="/*"
              element={
                <RequireAuth>
                  <Chat />
                </RequireAuth>
              }
            />
          </Routes>
        </BrowserRouter>
      </AntApp>
    </ConfigProvider>
  )
}
