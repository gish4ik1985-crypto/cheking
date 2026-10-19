import { createContext, useContext, useEffect, useState } from "react"

type Theme = "light" | "dark" | "system"
interface Ctx { theme: Theme; resolvedTheme: "light" | "dark"; setTheme: (t: Theme) => void }

const ThemeContext = createContext<Ctx>({ theme: "system", resolvedTheme: "light", setTheme: () => {} })
const KEY = "checking-theme"
const systemDark = () => window.matchMedia("(prefers-color-scheme: dark)").matches

function initial(): Theme {
  const q = new URLSearchParams(location.search).get("theme")
  if (q === "dark" || q === "light") return q
  try { const v = localStorage.getItem(KEY); if (v === "dark" || v === "light") return v } catch { /* без хранилища */ }
  return "system"
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setTheme] = useState<Theme>(initial)
  const [dark, setDark] = useState(systemDark)
  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)")
    const on = () => setDark(mq.matches)
    mq.addEventListener("change", on)
    return () => mq.removeEventListener("change", on)
  }, [])
  const resolvedTheme = theme === "system" ? (dark ? "dark" : "light") : theme
  useEffect(() => { document.documentElement.classList.toggle("dark", resolvedTheme === "dark") }, [resolvedTheme])
  const set = (t: Theme) => {
    setTheme(t)
    try { localStorage.setItem(KEY, t) } catch { /* без хранилища */ }
  }
  return <ThemeContext.Provider value={{ theme, resolvedTheme, setTheme: set }}>{children}</ThemeContext.Provider>
}

export const useTheme = () => useContext(ThemeContext)
