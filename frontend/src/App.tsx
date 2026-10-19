import { Navigate, Route, Routes, useLocation } from "react-router-dom"
import { useAuth } from "@/lib/auth"
import Shell from "@/components/shell"
import LoginPage from "@/pages/LoginPage"
import UploadPage from "@/pages/UploadPage"
import ReportPage from "@/pages/ReportPage"
import AdminPage from "@/pages/AdminPage"
import ProfilePage from "@/pages/ProfilePage"

export default function App() {
  const { me, loading } = useAuth()
  const loc = useLocation()
  const next = new URLSearchParams(loc.search).get("next") || "/"
  const dest = next.startsWith("/") && !next.startsWith("//") ? next : "/"
  if (loading) return <div className="grid min-h-screen place-items-center text-sm text-muted-foreground">Загрузка…</div>
  return (
    <Routes>
      <Route path="/login" element={me ? <Navigate to={dest} replace /> : <LoginPage />} />
      <Route element={me ? <Shell /> : <Navigate to="/login" replace />}>
        <Route path="/" element={<UploadPage />} />
        <Route path="/job/:id" element={<ReportPage />} />
        <Route path="/admin" element={<AdminPage />} />
        <Route path="/profile" element={<ProfilePage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
