import { useCallback, useEffect, useRef, useState } from "react"
import { Download, FileUp, Pencil, Plus, RefreshCw, Search, Trash2, X } from "lucide-react"
import { toast } from "sonner"
import { api, errText } from "@/lib/api"
import { details } from "@/lib/format"
import { useDialogs } from "@/components/dialogs"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Textarea } from "@/components/ui/textarea"
import { OkBadge, SevBadge } from "@/components/sev"
import { useAdmin } from "./context"

const Empty = ({ children }: { children: React.ReactNode }) => <p className="rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">{children}</p>
const Err = ({ children }: { children: React.ReactNode }) => <p className="rounded-md border border-[var(--sev-error)]/30 bg-[var(--sev-error-bg)] px-3 py-2 text-sm text-[var(--sev-error)]">{children}</p>

// ---------------------------------------------------------------- параметры
function NumField({ path, label, hint, scale = 1, step = "any", min, max }: { path: string; label: string; hint?: string; scale?: number; step?: string; min?: number; max?: number }) {
  const { params, setParams } = useAdmin()
  const get = () => path.split(".").reduce((o: any, k) => (o || {})[k], params)
  const v = get()
  const [text, setText] = useState(v == null ? "" : String(+(v * scale).toFixed(6)))
  const external = v == null ? "" : String(+(v * scale).toFixed(6))
  // значение изменилось снаружи (сброс) — обновить поле
  useEffect(() => { if (parseFloat(text.replace(",", ".")) !== parseFloat(external)) setText(external) }, [external]) // eslint-disable-line react-hooks/exhaustive-deps
  const on = (s: string) => {
    setText(s)
    const n = parseFloat(s.replace(",", "."))
    if (isNaN(n)) return
    setParams(p => {
      const c = JSON.parse(JSON.stringify(p))
      const ks = path.split(".")
      let o = c
      for (const k of ks.slice(0, -1)) o = o[k] = o[k] || {}
      o[ks[ks.length - 1]] = n / scale
      return c
    })
  }
  return (
    <div className="grid content-start gap-1.5">
      <Label htmlFor={"p-" + path}>{label}</Label>
      <Input id={"p-" + path} type="number" step={step} min={min} max={max} value={text} onChange={e => on(e.target.value)} />
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
    </div>
  )
}

export function ParamsTab() {
  const { params, setParams } = useAdmin()
  return (
    <div className="grid gap-4">
      <Card>
        <CardHeader><CardTitle>Масса</CardTitle></CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-3">
          <NumField path="mass.rel_tol" scale={100} step="0.5" min={0} label="Допустимое расхождение со спецификацией/ERP, %" />
          <NumField path="mass.abs_tol" step="0.001" min={0} label="…но не меньше, кг" />
          <NumField path="mass.min_fill" scale={100} step="1" min={0} label="Подозрительно малая масса: меньше % от габаритной заготовки" />
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>Технологичность</CardTitle></CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <NumField path="laser.hole_min_ratio" step="0.1" min={0} label="Отверстие на листе не меньше k × толщина, k =" hint="1 — осторожное правило; мощные волоконные лазеры режут ≈0,5–0,8·s" />
          <NumField path="laser.it_limit" step="1" min={5} max={16} label="На листовой детали допуски точнее IT… требуют мехобработки" />
          <NumField path="tight_it" step="1" min={1} max={10} label="«Очень жёсткий» допуск: IT не грубее" />
          <NumField path="coarse_it" step="1" min={12} max={18} label="«Подозрительно грубый» допуск: грубее IT" />
          <NumField path="thread_min_turns" step="0.5" min={1} label="Минимум витков резьбы в листе" />
          <NumField path="hardness_min_range_hrc" step="1" min={1} label="Минимальный диапазон твёрдости, ед. HRC" />
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>Распознавание</CardTitle></CardHeader>
        <CardContent>
          <label className="flex items-center gap-3 text-sm">
            <Switch checked={!!params.ocr} onCheckedChange={v => setParams(p => ({ ...p, ocr: v }))} />Распознавать сканы (OCR) по умолчанию
          </label>
        </CardContent>
      </Card>
    </div>
  )
}

// ---------------------------------------------------------------- справочники
export function ListsTab() {
  const { S, lists, setLists } = useAdmin()
  const lines = (k: "org_codes" | "general_tolerance_refs") => (lists[k] || []).join("\n")
  const setLines = (k: "org_codes" | "general_tolerance_refs", t: string) => setLists(l => ({ ...l, [k]: t.split("\n").map(s => s.trim()).filter(Boolean) }))
  const [txt, setTxt] = useState({ org_codes: lines("org_codes"), general_tolerance_refs: lines("general_tolerance_refs") })
  const obs = lists.obsolete_standards
  const setObs = (f: (o: typeof obs) => typeof obs) => setLists(l => ({ ...l, obsolete_standards: f(l.obsolete_standards) }))
  return (
    <div className="grid gap-4">
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader><CardTitle>Коды организаций</CardTitle><CardDescription>Обозначения с этими кодами проверяются на структуру по ГОСТ 2.201 (по одному в строке).</CardDescription></CardHeader>
          <CardContent><Textarea rows={6} value={txt.org_codes} onChange={e => { setTxt(t => ({ ...t, org_codes: e.target.value })); setLines("org_codes", e.target.value) }} /></CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>Ссылки на общие допуски</CardTitle><CardDescription>Если в ТТ есть одна из этих фраз — неуказанные предельные отклонения считаются оговорёнными (D10).</CardDescription></CardHeader>
          <CardContent><Textarea rows={6} value={txt.general_tolerance_refs} onChange={e => { setTxt(t => ({ ...t, general_tolerance_refs: e.target.value })); setLines("general_tolerance_refs", e.target.value) }} /></CardContent>
        </Card>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Заменённые редакции стандартов <span className="text-sm font-normal text-muted-foreground">(правило N01)</span></CardTitle>
          <CardDescription>Ссылка на «старую» редакцию на чертеже → замечание с указанием действующей. Добавьте свои строки, если на предприятии принят другой перечень.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3">
          <div className="overflow-hidden rounded-lg border">
            <Table>
              <TableHeader><TableRow><TableHead>Старая редакция</TableHead><TableHead>Действующая</TableHead><TableHead className="w-12" /></TableRow></TableHeader>
              <TableBody>
                {obs.map((r, i) => (
                  <TableRow key={i}>
                    <TableCell><Input value={r.old} onChange={e => setObs(o => o.map((x, j) => (j === i ? { ...x, old: e.target.value } : x)))} /></TableCell>
                    <TableCell><Input value={r.new} onChange={e => setObs(o => o.map((x, j) => (j === i ? { ...x, new: e.target.value } : x)))} /></TableCell>
                    <TableCell><Button variant="ghost" size="icon-sm" title="Удалить" onClick={() => setObs(o => o.filter((_, j) => j !== i))}><X /></Button></TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => setObs(o => [...o, { old: "ГОСТ ", new: "ГОСТ " }])}><Plus />Добавить строку</Button>
            <Button variant="outline" onClick={() => setObs(() => JSON.parse(JSON.stringify(S.default_obsolete)))}>Восстановить встроенный список</Button>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

// ---------------------------------------------------------------- исключения
export function ExceptionsTab() {
  const [list, setList] = useState<any[] | null>(null)
  const load = useCallback(() => { api<any[]>("/api/exceptions").then(setList).catch(() => setList([])) }, [])
  useEffect(load, [load])
  return (
    <Card>
      <CardHeader><CardTitle>Замечания, отмеченные «не ошибка»</CardTitle><CardDescription>Отмечаются в отчёте у конкретного замечания. Удалите строку — замечание снова будет показываться.</CardDescription></CardHeader>
      <CardContent className="px-0">
        {list === null ? <p className="px-6 text-sm text-muted-foreground">Загрузка…</p> : list.length === 0 ? <div className="px-6"><Empty>Отмеченных замечаний нет</Empty></div> : (
          <Table>
            <TableHeader><TableRow><TableHead className="pl-6">Код</TableHead><TableHead>Замечание</TableHead><TableHead>Чертёж</TableHead><TableHead>Когда</TableHead><TableHead className="w-12 pr-6" /></TableRow></TableHeader>
            <TableBody>
              {list.map(r => (
                <TableRow key={r.id}>
                  <TableCell className="pl-6 font-mono">{r.code}</TableCell>
                  <TableCell className="whitespace-normal">{r.scope === "global" ? <><b>Правило отключено везде</b>{r.pattern ? ` (содержит «${r.pattern}»)` : ""}</> : r.message}</TableCell>
                  <TableCell className="font-mono text-xs">{r.designation || r.file || ""}</TableCell>
                  <TableCell className="text-muted-foreground">{r.created || ""}</TableCell>
                  <TableCell className="pr-6"><Button variant="ghost" size="icon-sm" title="Удалить" onClick={async () => { try { await api("/api/admin/exceptions/" + r.id, { method: "DELETE" }); load() } catch (e) { toast.error(errText(e)) } }}><Trash2 /></Button></TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  )
}

// ---------------------------------------------------------------- пользователи
interface User { name: string; role: "admin" | "user"; created: string; default_password?: boolean }
const ROLE = { admin: "администратор", user: "пользователь" }

export function UsersTab() {
  const dlg = useDialogs()
  const [list, setList] = useState<User[]>([])
  const [name, setName] = useState("")
  const [pwd, setPwd] = useState("")
  const [role, setRole] = useState<"user" | "admin">("user")
  const [msg, setMsg] = useState<{ ok: boolean; t: string } | null>(null)
  const load = useCallback(() => { api<User[]>("/api/admin/users").then(setList).catch(() => {}) }, [])
  useEffect(load, [load])
  const call = async (url: string, method: string, body?: unknown) => {
    try { await api(url, { method, json: body }); load() } catch (e) { toast.error(errText(e)) }
  }
  const create = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      await api("/api/admin/users", { json: { name, password: pwd, role } })
      setMsg({ ok: true, t: "Пользователь создан" }); setName(""); setPwd(""); load()
    } catch (x) { setMsg({ ok: false, t: errText(x) }) }
  }
  return (
    <Card>
      <CardHeader><CardTitle>Пользователи</CardTitle><CardDescription>Учётные записи создаёт администратор. Администратор видит все отчёты и действия, настраивает проверки.</CardDescription></CardHeader>
      <CardContent className="grid gap-5">
        <div className="overflow-hidden rounded-lg border">
          <Table>
            <TableHeader><TableRow><TableHead>Имя</TableHead><TableHead>Роль</TableHead><TableHead>Создан</TableHead><TableHead /></TableRow></TableHeader>
            <TableBody>
              {list.map(u => (
                <TableRow key={u.name}>
                  <TableCell><b>{u.name}</b>{u.default_password && <Badge variant="outline" className="ml-2 border-[var(--sev-warn)]/30 bg-[var(--sev-warn-bg)] text-[var(--sev-warn)]">пароль по умолчанию</Badge>}</TableCell>
                  <TableCell>{ROLE[u.role]}</TableCell><TableCell className="text-muted-foreground">{u.created}</TableCell>
                  <TableCell><div className="flex flex-wrap justify-end gap-1.5">
                    <Button variant="outline" size="sm" onClick={async () => { const p = await dlg.prompt(`Новый пароль для «${u.name}»`, "Не короче 4 символов"); if (p) void call("/api/admin/users/" + encodeURIComponent(u.name), "PATCH", { password: p }) }}>Сбросить пароль</Button>
                    <Button variant="outline" size="sm" onClick={() => void call("/api/admin/users/" + encodeURIComponent(u.name), "PATCH", { role: u.role === "admin" ? "user" : "admin" })}>{u.role === "admin" ? "Сделать пользователем" : "Сделать администратором"}</Button>
                    <Button variant="ghost" size="icon-sm" title="Удалить" onClick={async () => { if (await dlg.confirm(`Удалить пользователя «${u.name}»?`, "Его отчёты останутся.", { ok: "Удалить", danger: true })) void call("/api/admin/users/" + encodeURIComponent(u.name), "DELETE") }}><Trash2 /></Button>
                  </div></TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
        <form className="grid gap-3" onSubmit={create}>
          <h3 className="text-sm font-semibold">Новый пользователь</h3>
          <div className="flex flex-wrap items-center gap-2">
            <Input className="w-48" placeholder="Имя" autoComplete="off" value={name} onChange={e => setName(e.target.value)} />
            <Input className="w-48" type="password" placeholder="Пароль" autoComplete="new-password" value={pwd} onChange={e => setPwd(e.target.value)} />
            <Select value={role} onValueChange={v => setRole((v as "user" | "admin") ?? "user")}>
              <SelectTrigger className="w-44"><SelectValue>{(v: "user" | "admin") => ROLE[v]}</SelectValue></SelectTrigger>
              <SelectContent><SelectItem value="user">пользователь</SelectItem><SelectItem value="admin">администратор</SelectItem></SelectContent>
            </Select>
            <Button type="submit" disabled={!name || !pwd}>Создать</Button>
          </div>
          {msg && (msg.ok ? <p className="rounded-md bg-[var(--sev-ok-bg)] px-3 py-2 text-sm text-[var(--sev-ok)]">{msg.t}</p> : <Err>{msg.t}</Err>)}
        </form>
      </CardContent>
    </Card>
  )
}

// ---------------------------------------------------------------- нормативы
interface Norm { id: string; designation: string; title: string; pages: number; size: number; source: string; has_text: boolean }

export function NormsTab() {
  const dlg = useDialogs()
  const [list, setList] = useState<Norm[] | null>(null)
  const [err, setErr] = useState("")
  const [file, setFile] = useState<File | null>(null)
  const [des, setDes] = useState("")
  const [title, setTitle] = useState("")
  const [q, setQ] = useState("")
  const [found, setFound] = useState<any[] | string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const load = useCallback(async () => {
    try { setList(await api<Norm[]>("/api/admin/norms")) } catch { setErr("Не удалось загрузить список") }
  }, [])
  useEffect(() => { void load() }, [load])

  const add = async () => {
    if (!file) { toast.error("Выберите файл PDF"); return }
    const fd = new FormData()
    fd.append("file", file); fd.append("designation", des); fd.append("title", title)
    try {
      await api("/api/admin/norms", { form: fd })
      setFile(null); setDes(""); setTitle(""); if (fileRef.current) fileRef.current.value = ""
      toast.success("Норматив добавлен"); void load()
    } catch (e) { toast.error(errText(e)) }
  }
  const find = async () => {
    if (q.trim().length < 3) { setFound("Введите не меньше трёх знаков"); return }
    try { const a = await api<any[]>("/api/admin/norms/search?q=" + encodeURIComponent(q.trim())); setFound(a.length ? a : "Ничего не найдено") } catch (e) { setFound(errText(e)) }
  }
  const edit = (n: Norm) => dlg.form("Изменить норматив", [{ key: "designation", label: "Обозначение", value: n.designation }, { key: "title", label: "Название", value: n.title }],
    async v => { try { await api("/api/admin/norms/" + encodeURIComponent(n.id), { method: "PATCH", json: v }); void load(); return null } catch (e) { return errText(e) } })
  const del = async (n: Norm) => {
    if (!(await dlg.confirm(`Удалить файл «${n.id}»?`, undefined, { ok: "Удалить", danger: true }))) return
    try { await api("/api/admin/norms/" + encodeURIComponent(n.id), { method: "DELETE" }); void load() } catch (e) { toast.error(errText(e)) }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Нормативы</CardTitle>
        <CardDescription>Тексты стандартов в PDF, на которых основаны проверки. «Открыть» показывает стандарт, поиск ищет фразу по тексту всех стандартов. В отчёте у замечаний администратора есть ссылка «текст ГОСТ» — она открывает стандарт на нужной странице, чтобы обосновать замечание перед автором чертежа. Файлы, добавленные здесь, хранятся в папке data/standards и при обновлении программы не пропадают; файлы из поставки (метка «программа») удалить нельзя.</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4">
        <div className="flex flex-wrap items-center gap-2">
          <input ref={fileRef} type="file" accept=".pdf,application/pdf" className="hidden" onChange={e => setFile(e.target.files?.[0] ?? null)} />
          <Button variant="outline" onClick={() => fileRef.current?.click()}><FileUp />{file ? file.name : "Выбрать PDF"}</Button>
          <Input className="w-72" placeholder="Обозначение, например ГОСТ Р 2.316-2023" value={des} onChange={e => setDes(e.target.value)} />
          <Input className="w-72" placeholder="Название" value={title} onChange={e => setTitle(e.target.value)} />
          <Button onClick={() => void add()}>Добавить PDF</Button>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative"><Search className="pointer-events-none absolute left-2.5 top-2.5 size-4 text-muted-foreground" />
            <Input className="w-96 pl-8" placeholder="Поиск по тексту стандартов (от 3 знаков)" value={q} onChange={e => setQ(e.target.value)} onKeyDown={e => { if (e.key === "Enter") void find() }} /></div>
          <Button variant="outline" onClick={() => void find()}>Найти</Button>
        </div>
        {typeof found === "string" && <p className="text-sm text-muted-foreground">{found}</p>}
        {Array.isArray(found) && (
          <div className="overflow-hidden rounded-lg border"><Table>
            <TableHeader><TableRow><TableHead>Стандарт</TableHead><TableHead>Стр.</TableHead><TableHead>Фрагмент</TableHead></TableRow></TableHeader>
            <TableBody>{found.map((x, i) => (
              <TableRow key={i}><TableCell><a className="text-primary hover:underline" target="_blank" rel="noreferrer" href={`/norms/${encodeURIComponent(x.id)}#page=${x.page}`}>{x.designation}</a></TableCell><TableCell>{x.page}</TableCell><TableCell className="whitespace-normal text-xs">{x.snippet}</TableCell></TableRow>
            ))}</TableBody>
          </Table></div>
        )}
        {err && <Err>{err}</Err>}
        {list && (list.length === 0 ? <Empty>Нормативов нет</Empty> : (
          <div className="overflow-hidden rounded-lg border"><Table>
            <TableHeader><TableRow><TableHead>Обозначение</TableHead><TableHead>Название</TableHead><TableHead>Стр.</TableHead><TableHead>Размер</TableHead><TableHead>Источник</TableHead><TableHead /></TableRow></TableHeader>
            <TableBody>{list.map(x => (
              <TableRow key={x.id}>
                <TableCell><b>{x.designation}</b></TableCell>
                <TableCell className="whitespace-normal">{x.title}{!x.has_text && <span className="text-muted-foreground"> (скан без текста: поиск не работает)</span>}</TableCell>
                <TableCell>{x.pages}</TableCell><TableCell className="font-mono text-xs">{(x.size / 1048576).toFixed(1)} МБ</TableCell>
                <TableCell>{x.source === "user" ? "добавлен" : "программа"}</TableCell>
                <TableCell><div className="flex items-center justify-end gap-1">
                  <Button variant="outline" size="sm" render={<a href={"/norms/" + encodeURIComponent(x.id)} target="_blank" rel="noreferrer" />}><Download />Открыть</Button>
                  {x.source === "user" && <><Button variant="ghost" size="icon-sm" title="Изменить" onClick={() => edit(x)}><Pencil /></Button><Button variant="ghost" size="icon-sm" title="Удалить" onClick={() => void del(x)}><Trash2 /></Button></>}
                </div></TableCell>
              </TableRow>
            ))}</TableBody>
          </Table></div>
        ))}
      </CardContent>
    </Card>
  )
}

// ---------------------------------------------------------------- отметки тестеров
export function ReviewTab() {
  const [j, setJ] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const load = useCallback(async () => { setLoading(true); try { setJ(await api("/api/admin/feedback")) } catch { setJ(null) } setLoading(false) }, [])
  useEffect(() => { void load() }, [load])
  const none = j && !j.rules.length && !j.missed.length && !j.parse.length && !(j.comments || []).length
  const T = ({ head, rows }: { head: string[]; rows: React.ReactNode[][] }) => (
    <div className="overflow-hidden rounded-lg border"><Table>
      <TableHeader><TableRow>{head.map(h => <TableHead key={h}>{h}</TableHead>)}</TableRow></TableHeader>
      <TableBody>{rows.map((r, i) => <TableRow key={i}>{r.map((c, k) => <TableCell key={k} className="whitespace-normal align-top">{c}</TableCell>)}</TableRow>)}</TableBody>
    </Table></div>
  )
  const mono = (s: string) => <span className="font-mono text-xs">{s}</span>
  return (
    <Card>
      <CardHeader>
        <CardTitle>Отметки тестеров</CardTitle>
        <CardDescription>Что тестеры отметили в отчётах: замечания «верно» / «ложное», пропуски и ошибки разбора. Ложные срабатывания по правилам — основание ослабить или отключить правило; пропуски — задания на новые правила.</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4">
        <div className="flex flex-wrap gap-2">
          <Button render={<a href="/api/admin/export.zip" />}><Download />Выгрузить для разработки (ZIP)</Button>
          <Button variant="outline" title="Включая проверки без отметок" render={<a href="/api/admin/export.zip?all=1" />}>ZIP со всеми проверками</Button>
          <Button variant="outline" onClick={() => void load()}><RefreshCw />Обновить</Button>
        </div>
        {loading && <p className="text-sm text-muted-foreground">Загрузка…</p>}
        {none && <Empty>Отметок пока нет</Empty>}
        {j && !none && (
          <div className="grid gap-6">
            <section className="grid gap-2">
              <h3 className="text-sm font-semibold">Правила: что подтверждено и что названо ложным</h3>
              <p className="text-xs text-muted-foreground">Считаются отметки по текущей ревизии правила. Если поведение правила меняли, отметки по прежним ревизиям показаны отдельно («до изменения») и не входят в долю ложных. Отметки старых версий программы относятся к ревизии 1.</p>
              {j.rules.length ? <T head={["Код", "Правило", "Верно", "Ложное", "Неточно", "Доля ложных", "До изменения"]} rows={j.rules.map((r: any) => [
                <>{mono(r.code)}{!r.known && <Badge variant="outline" className="ml-1 text-[var(--sev-warn)]" title="Такого правила нет в этой версии программы">нет в версии</Badge>}</>,
                <>{r.title || ""}<p className="text-xs text-muted-foreground">{(r.example || "").slice(0, 120)}</p></>,
                r.ok, <b>{r.false}</b>, r.inexact, r.total ? Math.round(r.false_share * 100) + " %" : "—",
                <span className="text-xs text-muted-foreground">{r.old.total ? `ревизия <${r.rev}: верно ${r.old.ok}, ложное ${r.old.false}, неточно ${r.old.inexact}` : ""}</span>])} /> : <p className="text-sm text-muted-foreground">нет</p>}
            </section>
            <section className="grid gap-2">
              <h3 className="text-sm font-semibold">Комментарии администраторов к замечаниям ({(j.comments || []).length})</h3>
              {(j.comments || []).length ? <T head={["Когда", "Кто", "Чертёж", "Замечание", "Комментарий", "Как должно быть"]} rows={j.comments.map((e: any) => [
                mono(e.ts), e.user, mono(e.designation || e.file || ""), <>{mono(e.code || "")} {(e.message || "").slice(0, 140)}</>, e.comment || "", e.expected || ""])} /> : <p className="text-sm text-muted-foreground">нет</p>}
            </section>
            <section className="grid gap-2">
              <h3 className="text-sm font-semibold">Пропущено программой ({j.missed.length})</h3>
              {j.missed_groups.length > 0 && <div className="flex flex-wrap gap-1.5">{j.missed_groups.map(([g, n]: [string, number]) => <Badge key={g} variant="secondary">{g}: {n}</Badge>)}</div>}
              {j.missed.length ? <T head={["Когда", "Кто", "Чертёж", "Группа", "Что должно быть найдено"]} rows={j.missed.map((e: any) => [mono(e.ts), e.user, mono(e.designation || e.file || ""), e.group || "", e.comment])} /> : <p className="text-sm text-muted-foreground">нет</p>}
            </section>
            <section className="grid gap-2">
              <h3 className="text-sm font-semibold">Ошибки разбора ({j.parse.length})</h3>
              {j.parse.length ? <T head={["Когда", "Кто", "Чертёж", "Прочитано", "Как должно быть / комментарий"]} rows={j.parse.map((e: any) => [mono(e.ts), e.user, mono(e.designation || e.file || ""), mono(e.dim || ""), (e.expected ? e.expected + " — " : "") + e.comment])} /> : <p className="text-sm text-muted-foreground">нет</p>}
            </section>
            <p className="text-sm text-muted-foreground">Отметок по пользователям: {j.users.map(([u, n]: [string, number]) => `${u} — ${n}`).join("; ")}</p>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

// ---------------------------------------------------------------- журнал
export function LogTab() {
  const [users, setUsers] = useState<string[]>([])
  const [user, setUser] = useState("")
  const [list, setList] = useState<any[] | null>(null)
  useEffect(() => { api<{ name: string }[]>("/api/admin/users").then(u => setUsers(u.map(x => x.name))).catch(() => {}) }, [])
  const load = useCallback(async () => {
    try { setList(await api<any[]>("/api/admin/actions" + (user ? "?user=" + encodeURIComponent(user) : ""))) } catch { setList([]) }
  }, [user])
  useEffect(() => { void load() }, [load])
  return (
    <Card>
      <CardHeader><CardTitle>Журнал действий</CardTitle></CardHeader>
      <CardContent className="grid gap-3 px-0">
        <div className="flex items-center gap-2 px-6">
          <Select value={user || "_"} onValueChange={v => setUser(v === "_" ? "" : (v ?? ""))}>
            <SelectTrigger className="w-60"><SelectValue>{(v: string) => (v === "_" ? "все пользователи" : v)}</SelectValue></SelectTrigger>
            <SelectContent><SelectItem value="_">все пользователи</SelectItem>{users.map(u => <SelectItem key={u} value={u}>{u}</SelectItem>)}</SelectContent>
          </Select>
          <Button variant="outline" onClick={() => void load()}><RefreshCw />Обновить</Button>
        </div>
        {list === null ? <p className="px-6 text-sm text-muted-foreground">Загрузка…</p> : list.length === 0 ? <p className="px-6 text-sm text-muted-foreground">Записей нет</p> : (
          <Table>
            <TableHeader><TableRow><TableHead className="pl-6">Когда</TableHead><TableHead>Кто</TableHead><TableHead>Действие</TableHead><TableHead className="pr-6">Подробности</TableHead></TableRow></TableHeader>
            <TableBody>{list.map((x, i) => (
              <TableRow key={i}><TableCell className="pl-6 font-mono text-xs">{x.ts}</TableCell><TableCell>{x.user}</TableCell><TableCell>{x.action}</TableCell><TableCell className="whitespace-normal pr-6 text-muted-foreground">{details(x.detail)}</TableCell></TableRow>
            ))}</TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  )
}

export { OkBadge, SevBadge }
