import { useEffect, useState } from "react"
import { api, errText } from "@/lib/api"
import { useAuth } from "@/lib/auth"
import { details } from "@/lib/format"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { toast } from "sonner"

interface Act { ts: string; action: string; detail: unknown }

export default function ProfilePage() {
  const { me, reload } = useAuth()
  const [old, setOld] = useState("")
  const [pw, setPw] = useState("")
  const [pw2, setPw2] = useState("")
  const [err, setErr] = useState("")
  const [acts, setActs] = useState<Act[] | null>(null)

  useEffect(() => { api<Act[]>("/api/profile/activity").then(setActs).catch(() => setActs([])) }, [])

  const change = async (e: React.FormEvent) => {
    e.preventDefault()
    setErr("")
    if (pw !== pw2) { setErr("Новые пароли не совпадают"); return }
    try {
      await api("/api/profile/password", { json: { old, new: pw } })
      toast.success("Пароль изменён")
      setOld(""); setPw(""); setPw2("")
      void reload()
    } catch (x) { setErr(errText(x)) }
  }

  return (
    <div className="mx-auto grid max-w-3xl gap-4 p-4 md:p-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">Профиль</h1>
        <p className="text-sm text-muted-foreground">{me?.name} · {me?.role === "admin" ? "администратор" : "пользователь"} · с {me?.created}</p>
      </div>
      <Card>
        <CardHeader><CardTitle>Смена пароля</CardTitle><CardDescription>Новый пароль — не короче 4 символов.</CardDescription></CardHeader>
        <CardContent>
          <form className="grid max-w-sm gap-3" onSubmit={change}>
            <div className="grid gap-1.5"><Label htmlFor="old">Текущий пароль</Label><Input id="old" type="password" autoComplete="current-password" value={old} onChange={e => setOld(e.target.value)} /></div>
            <div className="grid gap-1.5"><Label htmlFor="new">Новый пароль</Label><Input id="new" type="password" autoComplete="new-password" value={pw} onChange={e => setPw(e.target.value)} /></div>
            <div className="grid gap-1.5"><Label htmlFor="new2">Новый пароль ещё раз</Label><Input id="new2" type="password" autoComplete="new-password" value={pw2} onChange={e => setPw2(e.target.value)} /></div>
            {err && <p className="rounded-md border border-[var(--sev-error)]/30 bg-[var(--sev-error-bg)] px-3 py-2 text-sm text-[var(--sev-error)]">{err}</p>}
            <div><Button type="submit" disabled={!old || !pw}>Сменить пароль</Button></div>
          </form>
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>Мои действия</CardTitle></CardHeader>
        <CardContent className="px-0">
          {acts === null ? <p className="px-6 text-sm text-muted-foreground">Загрузка…</p> : acts.length === 0 ? <p className="px-6 text-sm text-muted-foreground">Действий пока нет</p> : (
            <Table>
              <TableHeader><TableRow><TableHead className="pl-6">Когда</TableHead><TableHead>Действие</TableHead><TableHead className="pr-6">Подробности</TableHead></TableRow></TableHeader>
              <TableBody>
                {acts.slice(0, 100).map((a, i) => (
                  <TableRow key={i}>
                    <TableCell className="pl-6 font-mono text-xs">{a.ts}</TableCell><TableCell>{a.action}</TableCell>
                    <TableCell className="whitespace-normal pr-6 text-muted-foreground">{details(a.detail)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
