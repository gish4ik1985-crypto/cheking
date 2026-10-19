import { createContext, useCallback, useContext, useEffect, useState } from "react"
import { useLocation, useNavigate } from "react-router-dom"
import { api, AUTH_EVENT } from "@/lib/api"
import type { Me } from "@/lib/types"

interface Ctx {
  me: Me | null
  loading: boolean
  isAdmin: boolean
  reload: () => Promise<void>
  logout: () => Promise<void>
}

const AuthContext = createContext<Ctx>({ me: null, loading: true, isAdmin: false, reload: async () => {}, logout: async () => {} })
export const useAuth = () => useContext(AuthContext)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [me, setMe] = useState<Me | null>(null)
  const [loading, setLoading] = useState(true)
  const nav = useNavigate()
  const loc = useLocation()

  const reload = useCallback(async () => {
    try { setMe(await api<Me>("/api/me", { quiet: true })) } catch { setMe(null) }
    setLoading(false)
  }, [])

  useEffect(() => { void reload() }, [reload])

  useEffect(() => {
    const on = () => {
      setMe(null)
      if (location.pathname !== "/login") nav("/login?next=" + encodeURIComponent(location.pathname + location.search), { replace: true })
    }
    window.addEventListener(AUTH_EVENT, on)
    return () => window.removeEventListener(AUTH_EVENT, on)
  }, [nav])

  // без входа — на страницу входа
  useEffect(() => {
    if (!loading && !me && loc.pathname !== "/login") nav("/login?next=" + encodeURIComponent(loc.pathname + loc.search), { replace: true })
  }, [loading, me, loc.pathname, loc.search, nav])

  const logout = useCallback(async () => {
    try { await api("/api/logout", { method: "POST" }) } catch { /* уже вышли */ }
    setMe(null)
    nav("/login", { replace: true })
  }, [nav])

  return <AuthContext.Provider value={{ me, loading, isAdmin: me?.role === "admin", reload, logout }}>{children}</AuthContext.Provider>
}
