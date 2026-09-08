import axios from 'axios'

const client = axios.create({
  baseURL: '/api',
  timeout: 30_000,
})

// Attach JWT to every request + cache busting for GET
client.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  // GET 请求添加时间戳防止缓存
  if (config.method === 'get') {
    config.params = { ...config.params, _t: Date.now() }
  }
  return config
})

// Unwrap BaseResp and handle errors
client.interceptors.response.use(
  (res) => {
    const body = res.data
    if (body && typeof body === 'object' && 'code' in body) {
      if (body.code !== 0) {
        const err = new Error(body.message || '请求失败') as Error & { response: typeof res }
        err.response = res
        return Promise.reject(err)
      }
      res.data = body.data
    }
    return res
  },
  (err) => {
    if (err.response?.status === 401) {
      // 登录接口的 401 不应清除本地数据（密码错误场景）
      const isLoginRequest = err.config?.url?.includes('/auth/login')
      if (!isLoginRequest) {
        localStorage.removeItem('access_token')
        localStorage.removeItem('user_info')
        window.location.href = '/login'
      }
    }
    return Promise.reject(err)
  },
)

export default client
