import { createContext, useCallback, useContext, useRef, useState } from "react"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { errText } from "@/lib/api"

export interface Field {
  key: string
  label: string
  type?: "text" | "area" | "select" | "password"
  options?: string[]
  value?: string
  placeholder?: string
}

type Spec =
  | { kind: "confirm"; title: string; text?: string; ok?: string; danger?: boolean }
  | { kind: "alert"; title: string; text?: string }
  | { kind: "form"; title: string; hint?: string; fields: Field[]; ok?: string; onSave: (v: Record<string, string>) => Promise<string | null | void> }

interface Api {
  confirm: (title: string, text?: string, o?: { ok?: string; danger?: boolean }) => Promise<boolean>
  alert: (title: string, text?: string) => Promise<void>
  /** Форма с полями; onSave возвращает текст ошибки (диалог останется открытым) или null/undefined (закроется). */
  form: (title: string, fields: Field[], onSave: (v: Record<string, string>) => Promise<string | null | void>, o?: { hint?: string; ok?: string }) => void
  prompt: (title: string, label: string, value?: string) => Promise<string | null>
}

const Ctx = createContext<Api | null>(null)
export const useDialogs = () => {
  const c = useContext(Ctx)
  if (!c) throw new Error("DialogsProvider не подключён")
  return c
}

export function DialogsProvider({ children }: { children: React.ReactNode }) {
  const [spec, setSpec] = useState<Spec | null>(null)
  const [vals, setVals] = useState<Record<string, string>>({})
  const [err, setErr] = useState("")
  const [busy, setBusy] = useState(false)
  const resolver = useRef<((v: any) => void) | null>(null)

  const open = useCallback((s: Spec, init: Record<string, string> = {}) => {
    setVals(init)
    setErr("")
    setBusy(false)
    setSpec(s)
  }, [])
  const done = (v: any) => {
    resolver.current?.(v)
    resolver.current = null
    setSpec(null)
  }

  const api: Api = {
    confirm: (title, text, o) => new Promise(res => { resolver.current = res; open({ kind: "confirm", title, text, ...o }) }),
    alert: (title, text) => new Promise(res => { resolver.current = () => res(); open({ kind: "alert", title, text }) }),
    form: (title, fields, onSave, o) => {
      resolver.current = null
      open({ kind: "form", title, fields, onSave, ...o }, Object.fromEntries(fields.map(f => [f.key, f.value ?? f.options?.[0] ?? ""])))
    },
    prompt: (title, label, value = "") => new Promise(res => {
      resolver.current = res
      open({
        kind: "form", title, fields: [{ key: "v", label, value }],
        onSave: async v => { done(v.v.trim() || null) },
      }, { v: value })
    }),
  }

  const submit = async () => {
    if (spec?.kind !== "form") return
    setBusy(true)
    try {
      const e = await spec.onSave({ ...vals })
      if (e) { setErr(e); setBusy(false) } else if (resolver.current === null) setSpec(null)
    } catch (x) {
      setErr(errText(x))
      setBusy(false)
    }
  }
  const onOpenChange = (o: boolean) => { if (!o) done(spec?.kind === "confirm" ? false : null) }

  return (
    <Ctx.Provider value={api}>
      {children}
      <Dialog open={!!spec} onOpenChange={onOpenChange}>
        <DialogContent className="max-h-[92svh] overflow-y-auto sm:max-w-lg">
          {spec && (
            <>
              <DialogHeader>
                <DialogTitle>{spec.title}</DialogTitle>
                {spec.kind === "form" && spec.hint && <DialogDescription className="break-words">{spec.hint}</DialogDescription>}
                {spec.kind !== "form" && spec.text && <DialogDescription>{spec.text}</DialogDescription>}
              </DialogHeader>
              {spec.kind === "form" && (
                <form className="grid gap-3" onSubmit={e => { e.preventDefault(); void submit() }}>
                  {spec.fields.map((f, i) => (
                    <div key={f.key} className="grid gap-1.5">
                      <Label htmlFor={"dlg-" + f.key}>{f.label}</Label>
                      {f.type === "area" ? (
                        <Textarea id={"dlg-" + f.key} rows={4} autoFocus={i === 0} value={vals[f.key] ?? ""} placeholder={f.placeholder}
                          onChange={e => setVals(v => ({ ...v, [f.key]: e.target.value }))} />
                      ) : f.type === "select" ? (
                        <Select value={vals[f.key]} onValueChange={v => setVals(s => ({ ...s, [f.key]: v ?? "" }))}>
                          <SelectTrigger id={"dlg-" + f.key} className="w-full"><SelectValue /></SelectTrigger>
                          <SelectContent>{(f.options ?? []).map(o => <SelectItem key={o} value={o}>{o}</SelectItem>)}</SelectContent>
                        </Select>
                      ) : (
                        <Input id={"dlg-" + f.key} type={f.type === "password" ? "password" : "text"} autoFocus={i === 0}
                          value={vals[f.key] ?? ""} placeholder={f.placeholder}
                          onChange={e => setVals(v => ({ ...v, [f.key]: e.target.value }))} />
                      )}
                    </div>
                  ))}
                  {err && <p className="rounded-md border border-[var(--sev-error)]/30 bg-[var(--sev-error-bg)] px-3 py-2 text-sm text-[var(--sev-error)]">{err}</p>}
                  <DialogFooter>
                    <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Отмена</Button>
                    <Button type="submit" disabled={busy}>{spec.ok ?? "Сохранить"}</Button>
                  </DialogFooter>
                </form>
              )}
              {spec.kind === "confirm" && (
                <DialogFooter>
                  <Button variant="outline" onClick={() => done(false)}>Отмена</Button>
                  <Button variant={spec.danger ? "destructive" : "default"} onClick={() => done(true)}>{spec.ok ?? "Да"}</Button>
                </DialogFooter>
              )}
              {spec.kind === "alert" && (
                <DialogFooter><Button onClick={() => done(null)}>Понятно</Button></DialogFooter>
              )}
            </>
          )}
        </DialogContent>
      </Dialog>
    </Ctx.Provider>
  )
}
