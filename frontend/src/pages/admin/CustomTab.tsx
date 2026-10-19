import { useEffect, useState } from "react"
import { Pencil, Plus, Trash2 } from "lucide-react"
import { toast } from "sonner"
import { api, errText } from "@/lib/api"
import { jobWhen } from "@/lib/format"
import { useDialogs } from "@/components/dialogs"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Textarea } from "@/components/ui/textarea"
import { Badge } from "@/components/ui/badge"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { useAdmin } from "./context"

type Rule = Record<string, any>

const EXAMPLES: Record<string, [string, Rule]> = {
  grades: ["Ограничительный перечень марок стали", { title: "Марки стали по ограничительному перечню", kind: "allowed", what: "grade", applies: "parts", values: ["Ст3сп", "09Г2С", "20", "45", "40Х", "12Х18Н10Т"], severity: "warning" }],
  fields: ["Разрешённые поля допусков", { title: "Поля допусков по перечню предприятия", kind: "allowed", what: "field", applies: "drawings", values: ["H7", "H8", "H9", "H11", "h6", "h7", "h9", "h11", "js9", "k6", "f7", "g6", "e8"], severity: "info" }],
  sharp: ["«Острые кромки притупить» в ТТ деталей", { title: "Острые кромки притупить", kind: "text_required", where: "tt", match: "contains", pattern: "Острые кромки притупить", applies: "parts", severity: "info" }],
  org: ["Организация в основной надписи", { title: "Организация в основной надписи", kind: "field", field: "organization", check: "contains", value: "Беретта", applies: "drawings", severity: "warning" }],
  ra: ["Шероховатость не точнее Ra 0,8 без согласования", { title: "Шероховатость не точнее Ra 0,8 без согласования", kind: "limit", what: "ra_min", value: "0.8", applies: "drawings", severity: "warning", message: "Шероховатость {value} точнее Ra 0,8 — согласуйте с технологом" }],
}
const SEV = { error: "Ошибка", warning: "Предупреждение", info: "Замечание" } as Record<string, string>

function Pick({ value, onChange, map, id }: { value: string; onChange: (v: string) => void; map: Record<string, string>; id?: string }) {
  return (
    <Select value={value} onValueChange={v => onChange(v ?? "")}>
      <SelectTrigger id={id} className="w-full"><SelectValue>{(v: string) => map[v] ?? v}</SelectValue></SelectTrigger>
      <SelectContent>{Object.entries(map).map(([k, v]) => <SelectItem key={k} value={k}>{v}</SelectItem>)}</SelectContent>
    </Select>
  )
}
const Field = ({ label, hint, children, wide }: { label: React.ReactNode; hint?: string; children: React.ReactNode; wide?: boolean }) => (
  <div className={`grid content-start gap-1.5 ${wide ? "sm:col-span-2" : ""}`}><Label>{label}</Label>{children}{hint && <p className="text-xs text-muted-foreground">{hint}</p>}</div>
)

export default function CustomTab() {
  const { S, rules, reload, dirty } = useAdmin()
  const dlg = useDialogs()
  const M = S.custom_meta
  const [ed, setEd] = useState<Rule | null>(null)
  const [edCode, setEdCode] = useState("")
  const [jobs, setJobs] = useState<{ id: string; count: number }[]>([])
  const [job, setJob] = useState("")
  const [testOut, setTestOut] = useState<any>(null)
  const [testErr, setTestErr] = useState("")
  const [err, setErr] = useState("")

  useEffect(() => { api<any[]>("/api/history").then(setJobs).catch(() => {}) }, [])

  const open = (r: Rule | null) => {
    setEdCode(r?.code || "")
    const base = { title: "", kind: "allowed", applies: "all", material_contains: "", designation_prefix: "", when_tt: "", severity: "warning", message: "", ref: "", pattern: "", match: "contains", where: "tt", field: "organization", check: "contains", value: "", what: "grade", values: "" }
    const src = { ...(r || {}) }
    if (Array.isArray(src.values)) src.values = src.values.join("\n")
    setEd({ ...base, ...src })
    setTestOut(null); setTestErr(""); setErr("")
    requestAnimationFrame(() => document.getElementById("cr-editor")?.scrollIntoView({ behavior: "smooth", block: "start" }))
  }
  const set = (k: string, v: any) => setEd(e => ({ ...e!, [k]: v }))
  const setKind = (k: string) => setEd(e => ({ ...e!, kind: k, what: k === "limit" ? "it_min" : "grade", where: k === "text_required" ? "tt" : "all", value: "", pattern: "", values: "" }))

  const collect = () => {
    const e = ed!
    const r: Rule = { title: e.title, kind: e.kind, applies: e.applies, material_contains: e.material_contains, designation_prefix: e.designation_prefix, when_tt: e.when_tt, severity: e.severity, message: e.message, ref: e.ref }
    if (e.kind === "text_required" || e.kind === "text_forbidden") Object.assign(r, { pattern: e.pattern, match: e.match, where: e.where })
    if (e.kind === "field") Object.assign(r, { field: e.field, check: e.check, value: e.value })
    if (e.kind === "allowed" || e.kind === "forbidden") Object.assign(r, { what: e.what, values: String(e.values).split("\n").map(s => s.trim()).filter(Boolean) })
    if (e.kind === "limit") Object.assign(r, { what: e.what, value: e.value })
    if (edCode) r.code = edCode
    return r
  }
  const reloadSafe = async () => {
    if (dirty && !(await dlg.confirm("На вкладке «Проверки по стандартам» есть несохранённые изменения", "Они будут сброшены. Продолжить?", { ok: "Продолжить" }))) return
    await reload()
  }
  const save = async () => {
    try {
      await api("/api/admin/custom", { json: collect() })
      setEd(null)
      toast.success("Правило сохранено")
      await reloadSafe()
    } catch (e) { setErr(errText(e)) }
  }
  const test = async () => {
    setTestErr(""); setTestOut(null)
    if (!job) { setTestErr("Выберите отчёт"); return }
    try { setTestOut(await api("/api/admin/custom/test", { json: { rule: collect(), job_id: job } })) } catch (e) { setTestErr(errText(e)) }
  }
  const del = async (code: string) => {
    if (!(await dlg.confirm(`Удалить правило ${code}?`, undefined, { ok: "Удалить", danger: true }))) return
    try { await api("/api/admin/custom/" + code, { method: "DELETE" }); await reloadSafe() } catch (e) { toast.error(errText(e)) }
  }

  const summary = (r: Rule) => {
    const v = (r.values || []) as string[]
    const p: Record<string, () => string> = {
      text_required: () => `в ${M.where[r.where] || ""}: «${r.pattern}»`, text_forbidden: () => `в ${M.where[r.where] || ""}: «${r.pattern}»`,
      field: () => `${M.fields[r.field] || ""} ${M.checks[r.check] || ""} ${r.check !== "filled" ? "«" + (r.value || "") + "»" : ""}`,
      allowed: () => `${M.list_what[r.what] || ""}: ${v.slice(0, 8).join(", ")}${v.length > 8 ? "…" : ""}`,
      forbidden: () => `${M.list_what[r.what] || ""}: ${v.slice(0, 8).join(", ")}`, limit: () => `${M.limit_what[r.what] || ""} ${r.value}`,
    }
    return `${M.kinds[r.kind] || r.kind}${p[r.kind] ? " — " + p[r.kind]() : ""}`
  }

  const list = S.custom_rules || []
  return (
    <div className="grid gap-4">
      <Card>
        <CardHeader>
          <CardTitle>Правила предприятия</CardTitle>
          <CardDescription>Свои проверки без программирования: обязательный или запрещённый текст, требования к графам основной надписи, ограничительные перечни (марки сталей, поля допусков, резьбы, стандарты), предельные значения. Правила попадают в общий список (группа «Правила предприятия»), там их можно включать и выключать. Новое правило сразу действует и на уже сохранённые отчёты.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4">
          <div className="flex flex-wrap items-center gap-2">
            <Button onClick={() => open(null)}><Plus />Добавить правило</Button>
            <Select value="" onValueChange={v => { const ex = EXAMPLES[v ?? ""]; if (ex) open(JSON.parse(JSON.stringify(ex[1]))) }}>
              <SelectTrigger className="w-72"><SelectValue placeholder="Начать с примера…" /></SelectTrigger>
              <SelectContent>{Object.entries(EXAMPLES).map(([k, [t]]) => <SelectItem key={k} value={k}>{t}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          {list.length === 0 ? <p className="rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">Своих правил пока нет</p> : (
            <div className="overflow-hidden rounded-lg border">
              <Table>
                <TableHeader><TableRow><TableHead>Код</TableHead><TableHead>Правило</TableHead><TableHead className="w-24" /></TableRow></TableHeader>
                <TableBody>
                  {list.map((r: Rule) => {
                    const off = rules[r.code] && !rules[r.code].enabled
                    const scope = [M.applies[r.applies || "all"], r.material_contains ? "материал: " + r.material_contains : "", r.designation_prefix ? "обозначение: " + r.designation_prefix + "…" : "", r.when_tt ? "если в тексте: " + r.when_tt : ""].filter(Boolean).join(" · ")
                    return (
                      <TableRow key={r.code} className={off ? "opacity-60" : ""}>
                        <TableCell><Badge variant="secondary" className="font-mono">{r.code}</Badge></TableCell>
                        <TableCell className="whitespace-normal">
                          <b>{r.title}</b>
                          <p className="text-xs text-muted-foreground">{summary(r)}</p>
                          <p className="text-xs text-muted-foreground">{scope} · {SEV[r.severity] || ""}{off ? " · выключено" : ""}{r.ref ? " · " + r.ref : ""}</p>
                        </TableCell>
                        <TableCell><div className="flex gap-1">
                          <Button variant="ghost" size="icon-sm" title="Изменить" onClick={() => open(r)}><Pencil /></Button>
                          <Button variant="ghost" size="icon-sm" title="Удалить" onClick={() => void del(r.code)}><Trash2 /></Button>
                        </div></TableCell>
                      </TableRow>
                    )
                  })}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      {ed && (
        <Card id="cr-editor">
          <CardHeader><CardTitle>{edCode ? `Правило ${edCode}` : "Новое правило"}</CardTitle></CardHeader>
          <CardContent className="grid gap-5">
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Название"><Input value={ed.title} onChange={e => set("title", e.target.value)} placeholder="Например: «Марки стали по перечню СТП 01»" /></Field>
              <Field label="Тип проверки"><Pick value={ed.kind} onChange={setKind} map={M.kinds} /></Field>
              {(ed.kind === "text_required" || ed.kind === "text_forbidden") && (<>
                <Field label="Что искать"><Input value={ed.pattern} onChange={e => set("pattern", e.target.value)} placeholder="Острые кромки притупить" /></Field>
                <Field label="Как искать"><Pick value={ed.match} onChange={v => set("match", v)} map={{ contains: "содержит текст (без учёта регистра)", regex: "регулярное выражение" }} /></Field>
                <Field label="Где"><Pick value={ed.where} onChange={v => set("where", v)} map={M.where} /></Field>
              </>)}
              {ed.kind === "field" && (<>
                <Field label="Графа"><Pick value={ed.field} onChange={v => set("field", v)} map={M.fields} /></Field>
                <Field label="Условие"><Pick value={ed.check} onChange={v => set("check", v)} map={M.checks} /></Field>
                {ed.check !== "filled" && <Field label="Значение"><Input value={ed.value} onChange={e => set("value", e.target.value)} /></Field>}
              </>)}
              {(ed.kind === "allowed" || ed.kind === "forbidden") && (<>
                <Field label="Что проверять"><Pick value={ed.what} onChange={v => set("what", v)} map={M.list_what} /></Field>
                <Field wide label={`${ed.kind === "allowed" ? "Разрешённые" : "Запрещённые"} значения — по одному в строке`}>
                  <Textarea rows={6} value={ed.values} onChange={e => set("values", e.target.value)} />
                </Field>
              </>)}
              {ed.kind === "limit" && (<>
                <Field label="Что ограничивать"><Pick value={ed.what} onChange={v => set("what", v)} map={M.limit_what} /></Field>
                <Field label="Значение"><Input type="number" step="any" value={ed.value ?? ""} onChange={e => set("value", e.target.value)} /></Field>
              </>)}
            </div>

            <div className="grid gap-3">
              <h3 className="text-sm font-semibold">К каким документам применять</h3>
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="Документы"><Pick value={ed.applies} onChange={v => set("applies", v)} map={M.applies} /></Field>
                <Field label="…если материал содержит (необязательно)"><Input value={ed.material_contains} onChange={e => set("material_contains", e.target.value)} placeholder="09Г2С" /></Field>
                <Field label="…если обозначение начинается с (необязательно)"><Input value={ed.designation_prefix} onChange={e => set("designation_prefix", e.target.value)} placeholder="ДТМЛ." /></Field>
                <Field label="…если в тексте чертежа есть (регулярное выражение, необязательно)"><Input value={ed.when_tt} onChange={e => set("when_tt", e.target.value)} placeholder="ОСТ\s*4\s*Г[О0]\.?070\.?014" /></Field>
              </div>
            </div>

            <div className="grid gap-3">
              <h3 className="text-sm font-semibold">Замечание</h3>
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="Важность"><Pick value={ed.severity} onChange={v => set("severity", v)} map={SEV} /></Field>
                <Field label="Ссылка на документ (необязательно)"><Input value={ed.ref} onChange={e => set("ref", e.target.value)} placeholder="СТП 01-2025 п. 4.2" /></Field>
                <Field wide label="Текст замечания" hint="Пусто — сформируется сам; {value} — найденное значение"><Input value={ed.message} onChange={e => set("message", e.target.value)} /></Field>
              </div>
            </div>

            <div className="grid gap-3">
              <h3 className="text-sm font-semibold">Проверить перед сохранением</h3>
              <div className="flex flex-wrap items-center gap-2">
                <Select value={job} onValueChange={v => setJob(v ?? "")}>
                  <SelectTrigger className="w-72"><SelectValue placeholder="Выберите сохранённый отчёт…">{(v: string) => { const j = jobs.find(x => x.id === v); return j ? `${jobWhen(j.id)} — ${j.count} док.` : v }}</SelectValue></SelectTrigger>
                  <SelectContent>{jobs.map(j => <SelectItem key={j.id} value={j.id}>{jobWhen(j.id)} — {j.count} док.</SelectItem>)}</SelectContent>
                </Select>
                <Button variant="outline" onClick={() => void test()}>Проверить на отчёте</Button>
              </div>
              {testErr && <p className="rounded-md border border-[var(--sev-error)]/30 bg-[var(--sev-error-bg)] px-3 py-2 text-sm text-[var(--sev-error)]">{testErr}</p>}
              {testOut && (
                <div className="grid gap-2">
                  <p className="rounded-md bg-muted px-3 py-2 text-sm">Проверено документов: {testOut.checked}. Замечаний: {testOut.total}{testOut.total > testOut.hits.length ? ` (показаны первые ${testOut.hits.length})` : ""}</p>
                  {testOut.hits.length > 0 && (
                    <div className="overflow-hidden rounded-lg border"><Table>
                      <TableHeader><TableRow><TableHead>Документ</TableHead><TableHead>Замечание</TableHead></TableRow></TableHeader>
                      <TableBody>{testOut.hits.map((h: any, i: number) => <TableRow key={i}><TableCell className="font-mono text-xs">{h.designation || h.file}</TableCell><TableCell className="whitespace-normal">{h.message}</TableCell></TableRow>)}</TableBody>
                    </Table></div>
                  )}
                </div>
              )}
            </div>

            {err && <p className="rounded-md border border-[var(--sev-error)]/30 bg-[var(--sev-error-bg)] px-3 py-2 text-sm text-[var(--sev-error)]">{err}</p>}
            <div className="flex gap-2"><Button onClick={() => void save()}>Сохранить правило</Button><Button variant="outline" onClick={() => setEd(null)}>Отмена</Button></div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
