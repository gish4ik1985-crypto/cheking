import { useState } from "react"
import { FileCheck2 } from "lucide-react"
import { api, errText } from "@/lib/api"
import { useAuth } from "@/lib/auth"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

export default function LoginPage() {
  const { reload } = useAuth()
  const [name, setName] = useState("")
  const [pwd, setPwd] = useState("")
  const [err, setErr] = useState("")
  const [busy, setBusy] = useState(false)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setErr("")
    try {
      await api("/api/login", { json: { name, password: pwd }, quiet: true })
      await reload()
    } catch (x) {
      setErr(errText(x))
      setBusy(false)
    }
  }

  return (
    <div className="grid min-h-screen place-items-center bg-muted/40 p-4">
      <Card className="w-full max-w-sm">
        <CardHeader className="justify-items-center text-center">
          <div className="mb-2 grid size-12 place-items-center rounded-xl bg-primary text-primary-foreground"><FileCheck2 className="size-6" /></div>
          <CardTitle className="text-xl">Проверка чертежей</CardTitle>
          <CardDescription>Войдите под своим именем. Учётную запись создаёт администратор.</CardDescription>
        </CardHeader>
        <CardContent>
          <form className="grid gap-4" onSubmit={submit}>
            <div className="grid gap-1.5">
              <Label htmlFor="name">Имя пользователя</Label>
              <Input id="name" autoComplete="username" autoFocus value={name} onChange={e => setName(e.target.value)} />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="pwd">Пароль</Label>
              <Input id="pwd" type="password" autoComplete="current-password" value={pwd} onChange={e => setPwd(e.target.value)} />
            </div>
            {err && <p className="rounded-md border border-[var(--sev-error)]/30 bg-[var(--sev-error-bg)] px-3 py-2 text-sm text-[var(--sev-error)]">{err}</p>}
            <Button type="submit" disabled={busy || !name}>Войти</Button>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
