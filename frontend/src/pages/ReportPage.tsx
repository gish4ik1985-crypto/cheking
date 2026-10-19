import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { Link, useNavigate, useParams } from "react-router-dom"
import { ChevronDown, ChevronUp, FileSpreadsheet, FileText, FilePlus2, ListChecks, PanelLeftClose, PanelLeftOpen, Search, Target, Eye } from "lucide-react"
import { toast } from "sonner"
import { api, errText } from "@/lib/api"
import { num } from "@/lib/format"
import { useDialogs } from "@/components/dialogs"
import type { Completeness, DocResult, FbEntry, JobFull, Sev } from "@/lib/types"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Counts, OkBadge, SevBadge, SEV_LABEL } from "@/components/sev"
import Viewer, { type NFinding, type ViewerHandle } from "./report/Viewer"
import FindingsTab from "./report/FindingsTab"
import { DimsTab, FbTab, LimitsTab, OpsTab, RowsTab, TitleTab, TtTab } from "./report/OtherTabs"

const STATUS: Record<string, { sev: Sev | "ok"; text: string }> = {
  ok: { sev: "ok", text: "Без замечаний" }, warnings: { sev: "warning", text: "Проверить" }, errors: { sev: "error", text: "Есть ошибки" },
  missing: { sev: "error", text: "НЕТ ЧЕРТЕЖА" }, not_required: { sev: "info", text: "не требуется" },
}

const sortOrder = (data: DocResult[]) =>
  data.map((_, i) => i).sort((a, b) => (data[b].counts.error - data[a].counts.error) || (data[b].counts.warning - data[a].counts.warning) || a - b)

function CompView({ comp, onOpen }: { comp: Completeness; onOpen: (docId: number) => void }) {
  const rows = comp.rows.filter(r => r.need || r.status !== "not_required")
  return (
    <div className="grid content-start gap-3 overflow-auto p-1">
      <div>
        <h2 className="text-lg font-semibold tracking-tight">Комплектность по спецификации</h2>
        <p className="text-sm text-muted-foreground">Позиции СП, которым положен чертёж (детали и сборочные единицы), и результат проверки их чертежей</p>
      </div>
      <div className="flex flex-wrap gap-2">
        <SevBadge sev="error">Нет чертежа: {comp.stats.missing}</SevBadge>
        <SevBadge sev="error">С ошибками: {comp.stats.errors}</SevBadge>
        <SevBadge sev="warning">Проверить: {comp.stats.warnings}</SevBadge>
        <OkBadge>Без замечаний: {comp.stats.ok}</OkBadge>
      </div>
      <Card className="overflow-hidden">
        <Table>
          <TableHeader><TableRow><TableHead>Поз.</TableHead><TableHead>Обозначение</TableHead><TableHead>Наименование</TableHead><TableHead>Раздел</TableHead><TableHead>Статус</TableHead><TableHead>Файл</TableHead></TableRow></TableHeader>
          <TableBody>
            {rows.map((r, i) => {
              const s = STATUS[r.status]
              return (
                <TableRow key={i} className={r.doc_id !== null ? "cursor-pointer" : ""} onClick={() => r.doc_id !== null && onOpen(r.doc_id)}>
                  <TableCell>{r.pos}</TableCell><TableCell className="font-mono text-xs">{r.designation || r.sku}</TableCell>
                  <TableCell className="whitespace-normal">{r.name}</TableCell><TableCell>{r.section}</TableCell>
                  <TableCell>{s.sev === "ok" ? <OkBadge>{s.text}</OkBadge> : <SevBadge sev={s.sev}>{s.text}{r.errors ? " · " + r.errors : ""}</SevBadge>}</TableCell>
                  <TableCell className="text-muted-foreground">{r.file}</TableCell>
                </TableRow>
              )
            })}
            {comp.extra.map((x, i) => (
              <TableRow key={"x" + i}>
                <TableCell /><TableCell className="font-mono text-xs">{x.designation}</TableCell>
                <TableCell colSpan={2} className="text-muted-foreground">чертёж есть, а в спецификации позиции нет</TableCell>
                <TableCell><SevBadge sev="warning">нет в СП</SevBadge></TableCell><TableCell className="text-muted-foreground">{x.file}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>
    </div>
  )
}

function kvOf(d: DocResult): [string, string][] {
  const t = d.title, facts = d.facts || {}
  const isSpec = d.kind === "spec", isProc = d.kind === "process"
  const pr = facts.process || {}
  let kv: [string, string][]
  if (isProc) kv = [["Файл", d.file], ["Вид документа", pr.type_name], ["Обозначение детали", t.designation ?? ""], ["Наименование", t.name ?? ""],
    ["Материал", t.material ?? ""], ["Чертёж детали в проверке", pr.drawing || (t.designation ? "не найден" : "—")], ["Операций распознано", String((pr.operations || []).length)]]
  else if (isSpec) kv = [["Файл", d.file], ["Обозначение", t.designation ?? ""], ["Наименование", t.name ?? ""],
    ["Тип", facts.spec_document ? "спецификация (PDF) — проверка по ГОСТ 2.106" : "спецификация (проверка по ГОСТ 2.106)"],
    facts.spec_document ? ["Строк в таблице", String((facts.spec_rows || []).length)] : ["Сборочных единиц", String((facts.spec_tree || []).length)]]
  else kv = [["Файл", d.file + (d.sheets ? " · " + d.sheets : "")], ["Наименование", t.name ?? ""], ["Материал", t.material ?? ""],
    ["Масса", t.mass ? t.mass + " кг" + (facts.mass_ref ? ` (СП: ${num(+facts.mass_ref.toFixed(4))})` : "") : "—"],
    ["Масштаб / формат", [t.scale, t.format].filter(Boolean).join(" · ")],
    ["Габариты (оценка)", facts.overall ? Object.entries(facts.overall).map(([k, v]) => `${k}=${num(v as number)}`).join(" ") : "—"],
    ["Толщина листа", facts.sheet_thickness ? num(facts.sheet_thickness) + " мм" : "—"],
    ["Тип", (d.kind || "") + (d.ocr ? " · OCR" : "") + (facts.converted ? " · через " + facts.converted : "")]]
  const mp = facts.mass_parts
  if (mp && (mp.parts || mp.unknown)) kv.splice(4, 0, ["Масса частей", mp.parts
    ? `${num(mp.known)} кг по ${mp.parts} поз.` + (mp.unknown ? ` · без массы ${mp.unknown} поз.` : " · все известны") : `неизвестна (${mp.unknown} поз.)`])
  if (d.dxf) kv.push(["DXF", `${d.dxf.name} · ${num(d.dxf.size[0])}×${num(d.dxf.size[1])}`])
  if (d.welds?.length) kv.push(["Сварные швы", d.welds.map(w => w.raw).join("; ")])
  return kv
}

export default function ReportPage() {
  const { id: jobId = "" } = useParams()
  const nav = useNavigate()
  const dlg = useDialogs()
  const [job, setJob] = useState<JobFull | null>(null)
  const [fb, setFb] = useState<FbEntry[]>([])
  const [groups, setGroups] = useState<string[]>([])
  const [loadErr, setLoadErr] = useState("")
  const [cur, setCur] = useState<number | null>(null)       // id документа
  const [view, setView] = useState<"doc" | "comp">("doc")
  const [filters, setFilters] = useState<Record<Sev, boolean>>({ error: true, warning: true, info: true })
  const [tab, setTab] = useState("findings")
  const [selected, setSelected] = useState<number | null>(null)
  const [pick, setPick] = useState(false)
  const [kvOpen, setKvOpen] = useState(false)
  const [q, setQ] = useState("")
  const [docsOpen, setDocsOpen] = useState(() => { try { return localStorage.getItem("rep-side") !== "0" && window.innerWidth >= 1100 } catch { return true } })
  const [panelW, setPanelW] = useState(() => { try { return Number(localStorage.getItem("rep-panel-w")) || 460 } catch { return 460 } })
  const viewer = useRef<ViewerHandle>(null)
  const panelRef = useRef<HTMLDivElement>(null)
  const picked = useRef(false)

  const loadFb = useCallback(async () => { try { setFb(await api<FbEntry[]>(`/api/jobs/${jobId}/feedback`)) } catch { setFb([]) } }, [jobId])

  const load = useCallback(async () => {
    try {
      const j = await api<JobFull>(`/api/jobs/${jobId}?full=1`)
      setJob(j)
      setLoadErr("")
      const data = j.results || []
      if (!picked.current && j.state !== "running") {
        picked.current = true
        if (j.completeness) setView("comp")
        else if (data.length) setCur(data[sortOrder(data)[0]].id)
      }
      return j
    } catch (e) { setLoadErr(errText(e)); return null }
  }, [jobId])

  useEffect(() => {
    picked.current = false
    setJob(null); setCur(null); setView("doc"); setSelected(null)
    void loadFb()
    api<{ groups: string[] }>("/api/feedback/meta").then(m => setGroups(m.groups)).catch(() => {})
    let timer: ReturnType<typeof setTimeout>
    const tick = async () => { const j = await load(); if (j?.state === "running") timer = setTimeout(tick, 1500) }
    void tick()
    return () => clearTimeout(timer)
  }, [jobId, load, loadFb])

  const data = useMemo(() => job?.results || [], [job])
  const comp = job?.completeness ?? null
  const doc = data.find(d => d.id === cur) ?? null
  const order = useMemo(() => sortOrder(data), [data])
  const totals = useMemo(() => data.reduce((a, d) => ({ error: a.error + d.counts.error, warning: a.warning + d.counts.warning, info: a.info + d.counts.info }), { error: 0, warning: 0, info: 0 }), [data])

  const findings: NFinding[] = useMemo(() => (doc ? doc.findings.map((f, i) => ({ ...f, n: i + 1 })).filter(f => filters[f.severity]) : []), [doc, filters])
  const isSpec = doc?.kind === "spec", isProc = doc?.kind === "process"
  const specDoc = !!doc?.facts?.spec_document
  const hasViewer = !!doc?.pages.some(p => p.image)
  const docFb = doc ? fb.filter(e => e.doc === doc.id) : []

  const tabs = useMemo(() => {
    if (!doc) return []
    const f: [string, string] = ["findings", `Замечания (${findings.length})`]
    const o: [string, string] = ["fb", `Отметки (${docFb.length})`]
    if (isProc) return [f, ["ops", `Операции (${(doc.facts?.process?.operations || []).length})`], o]
    if (isSpec && specDoc) return [f, ["rows", `Строки (${(doc.facts?.spec_rows || []).length})`], o]
    return [f, ["dims", `Размеры (${doc.dims.length})`], ["limits", "Допуски"], ["title", "Основная надпись"], ["tt", `ТТ (${doc.tt.length})`], o]
  }, [doc, findings.length, docFb.length, isProc, isSpec, specDoc])
  useEffect(() => { if (tabs.length && !tabs.some(t => t[0] === tab)) setTab("findings") }, [tabs, tab])

  const select = (n: number | null) => {
    setSelected(n)
    if (n === null) return
    setTab("findings")
    requestAnimationFrame(() => {
      const el = document.getElementById(`finding-${n}`), pn = panelRef.current
      if (el && pn) {
        const r = el.getBoundingClientRect(), pr = pn.getBoundingClientRect()
        if (r.top < pr.top + 40 || r.bottom > pr.bottom) pn.scrollTo({ top: pn.scrollTop + r.top - pr.top - 60, behavior: "smooth" })
      }
    })
  }
  const openDoc = (id: number) => { setCur(id); setView("doc"); setSelected(null); setPick(false) }

  // горячие клавиши: J/K — замечания, +/−/0 — масштаб, Esc — отмена выбора места
  useEffect(() => {
    const on = (ev: KeyboardEvent) => {
      if (ev.key === "Escape" && pick) { setPick(false); return }
      const t = ev.target as HTMLElement
      if (t.closest("input, textarea, select, [role=dialog]") || ev.ctrlKey || ev.metaKey || ev.altKey) return
      const k = ev.key.toLowerCase()
      if (k === "j" || k === "о") viewer.current?.step(1)
      else if (k === "k" || k === "л") viewer.current?.step(-1)
      else if (k === "+" || k === "=") viewer.current?.zoomBy(1.3)
      else if (k === "-") viewer.current?.zoomBy(1 / 1.3)
      else if (k === "0") viewer.current?.reset()
    }
    window.addEventListener("keydown", on)
    return () => window.removeEventListener("keydown", on)
  }, [pick])

  const sendFb = async (rec: Record<string, unknown>): Promise<string | null> => {
    if (!doc) return "Нет документа"
    try {
      await api(`/api/jobs/${jobId}/feedback`, { json: { doc: doc.id, file: doc.file, designation: doc.title.designation, ...rec } })
      await loadFb()
      return null
    } catch (e) { return errText(e) }
  }
  const parseDlg = (dim: string) => dlg.form("Неверно прочитано", [
    { key: "dim", label: "Как прочитала программа (размер, допуск, поле штампа)", value: dim },
    { key: "expected", label: "Как должно быть", placeholder: "Например: ⌀295,7 -0,1" },
    { key: "comment", label: "Комментарий", type: "area" },
  ], async v => (v.expected || v.comment) ? sendFb({ type: "parse", dim: v.dim, expected: v.expected, comment: v.comment || "прочитано неверно" }) : "Укажите, как должно быть, или напишите комментарий",
  { hint: "Такие отметки помогают исправить разбор текста чертежа" })

  const onPick = (page: number, point: [number, number]) => {
    setPick(false)
    dlg.form("Программа не заметила", [
      { key: "group", label: "К какой группе относится", type: "select", options: groups.length ? groups : ["Другое"] },
      { key: "comment", label: "Что должно было быть найдено?", type: "area", placeholder: "Например: размер 40 H7 — нет шероховатости посадочной поверхности" },
    ], v => sendFb({ type: "missed", page, point, group: v.group, comment: v.comment }), { hint: `Лист ${page + 1}, место отмечено на чертеже` })
  }
  const delFb = async (id: string) => {
    if (!(await dlg.confirm("Удалить отметку?", undefined, { ok: "Удалить", danger: true }))) return
    try { await api(`/api/jobs/${jobId}/feedback/${id}`, { method: "DELETE" }); await loadFb() } catch (e) { toast.error(errText(e)) }
  }

  // ширина правой панели
  const startResize = (ev: React.MouseEvent) => {
    ev.preventDefault()
    const x0 = ev.clientX, w0 = panelW
    let w = w0
    const mv = (e: MouseEvent) => { w = Math.max(320, Math.min(window.innerWidth * 0.7, w0 - (e.clientX - x0))); setPanelW(w) }
    const up = () => {
      window.removeEventListener("mousemove", mv); window.removeEventListener("mouseup", up)
      document.body.style.userSelect = ""
      try { localStorage.setItem("rep-panel-w", String(Math.round(w))) } catch { /* без хранилища */ }
    }
    document.body.style.userSelect = "none"
    window.addEventListener("mousemove", mv); window.addEventListener("mouseup", up)
  }
  const toggleDocs = () => { setDocsOpen(o => { try { localStorage.setItem("rep-side", o ? "0" : "1") } catch { /* без хранилища */ } return !o }) }

  const list = order.filter(i => {
    const d = data[i]
    return !q || (d.file + " " + d.title.designation + " " + d.title.name).toLowerCase().includes(q.toLowerCase())
  })

  if (loadErr && !job) return <div className="p-6"><p className="rounded-md border border-[var(--sev-error)]/30 bg-[var(--sev-error-bg)] p-4 text-sm text-[var(--sev-error)]">{loadErr}. <Link to="/" className="underline">К новой проверке</Link></p></div>
  if (!job) return <div className="p-6 text-sm text-muted-foreground">Загрузка отчёта…</div>

  const specInfo = job.spec ? ` · спецификация «${job.spec.name}» (${job.spec.items} поз.)` : ""
  const summary = doc ? [doc.title.mass ? `Масса ${doc.title.mass} кг` : "", [doc.title.scale, doc.title.format].filter(Boolean).join(" · "), doc.title.material].filter(Boolean) : []

  const panel = doc && (
    <div className="flex min-h-0 min-w-0 flex-col rounded-xl border bg-card" style={hasViewer ? { width: panelW } : undefined}>
      <div className="border-b p-2">
        <Tabs value={tab} onValueChange={setTab}>
          <TabsList className="h-auto w-full flex-wrap justify-start">
            {tabs.map(([k, v]) => <TabsTrigger key={k} value={k}>{v}</TabsTrigger>)}
          </TabsList>
        </Tabs>
      </div>
      <div ref={panelRef} className="min-h-0 flex-1 overflow-auto p-3">
        {doc.error && <p className="mb-3 whitespace-pre-wrap rounded-md border border-[var(--sev-error)]/30 bg-[var(--sev-error-bg)] p-3 text-sm text-[var(--sev-error)]">{doc.error}</p>}
        {!hasViewer && isSpec && !specDoc && (
          <Card className="mb-3 overflow-hidden">
            <Table>
              <TableHeader><TableRow><TableHead>Поз.</TableHead><TableHead>Сборочная единица</TableHead><TableHead>Составных частей</TableHead></TableRow></TableHeader>
              <TableBody>{(doc.facts?.spec_tree || []).map((n: any, i: number) => (
                <TableRow key={i}><TableCell className="font-mono">{n.pos || "—"}</TableCell><TableCell className="whitespace-normal"><span className="font-mono text-xs">{n.designation}</span> {n.name}</TableCell><TableCell>{n.children}</TableCell></TableRow>
              ))}</TableBody>
            </Table>
          </Card>
        )}
        {!hasViewer && !isSpec && !isProc && <p className="mb-3 rounded-md border border-dashed p-3 text-sm text-muted-foreground">Предпросмотр листа недоступен для этого формата ({doc.kind}).</p>}
        {tab === "findings" && <FindingsTab doc={doc} jobId={jobId} findings={findings} fb={fb} selected={selected} onSelect={select} onChanged={() => void load()} onFbChanged={() => void loadFb()} />}
        {tab === "dims" && <DimsTab doc={doc} onWrong={parseDlg} />}
        {tab === "limits" && <LimitsTab doc={doc} />}
        {tab === "title" && <TitleTab doc={doc} />}
        {tab === "tt" && <TtTab doc={doc} />}
        {tab === "ops" && <OpsTab doc={doc} />}
        {tab === "rows" && <RowsTab doc={doc} />}
        {tab === "fb" && <FbTab doc={doc} fb={fb} onDelete={id => void delFb(id)} />}
      </div>
    </div>
  )

  return (
    <div className="flex h-[calc(100svh-3.5rem)] min-h-[560px] flex-col gap-2 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="outline" size="sm" onClick={toggleDocs} title="Скрыть или показать список документов">
          {docsOpen ? <PanelLeftClose /> : <PanelLeftOpen />}Документы
        </Button>
        <div className="min-w-0">
          <h1 className="text-sm font-semibold">Отчёт проверки</h1>
          <p className="truncate text-xs text-muted-foreground">
            {data.length} док.{specInfo}{job.state === "running" ? ` · идёт проверка ${job.done}/${job.total}…` : ""}
            {job.warnings?.length ? <span className="text-[var(--sev-error)]"> · {job.warnings.join("; ")}</span> : null}
          </p>
        </div>
        <div className="ml-auto flex flex-wrap items-center gap-1.5">
          {(["error", "warning", "info"] as Sev[]).map(s => (
            <button key={s} onClick={() => setFilters(f => ({ ...f, [s]: !f[s] }))} title="Показать или скрыть" className={filters[s] ? "" : "opacity-40"}>
              <SevBadge sev={s}>{SEV_LABEL[s]} <b>{totals[s]}</b></SevBadge>
            </button>
          ))}
          <Button variant="outline" size="sm" render={<a href={`/api/jobs/${jobId}/excel`} />}><FileSpreadsheet />Excel</Button>
          <Button variant="outline" size="sm" title="Перечень замечаний для конструктора" render={<a href={`/api/jobs/${jobId}/remarks.docx`} />}><FileText />Word</Button>
          <Button variant="outline" size="sm" onClick={() => nav("/")}><FilePlus2 />Новая проверка</Button>
        </div>
      </div>

      <div className="flex min-h-0 flex-1 gap-3">
        {docsOpen && (
          <aside className="hidden w-72 shrink-0 flex-col rounded-xl border bg-card md:flex">
            <div className="relative border-b p-2">
              <Search className="pointer-events-none absolute left-4.5 top-4.5 size-4 text-muted-foreground" />
              <Input value={q} onChange={e => setQ(e.target.value)} placeholder="Поиск по обозначению, файлу…" className="pl-8" />
            </div>
            <ScrollArea className="min-h-0 flex-1">
              <div className="grid gap-0.5 p-1.5">
                {comp && (
                  <button onClick={() => setView("comp")} className={`grid gap-1 rounded-lg px-2.5 py-2 text-left transition hover:bg-accent ${view === "comp" ? "bg-accent" : ""}`}>
                    <span className="flex items-center gap-1.5 text-sm font-medium"><ListChecks className="size-4" />Комплектность по СП</span>
                    <span className="flex flex-wrap gap-1">
                      {comp.stats.missing > 0 && <SevBadge sev="error">нет чертежа: {comp.stats.missing}</SevBadge>}
                      {comp.stats.errors > 0 && <SevBadge sev="error">с ошибками: {comp.stats.errors}</SevBadge>}
                      <OkBadge>OK: {comp.stats.ok}</OkBadge>
                    </span>
                  </button>
                )}
                {list.map(i => {
                  const d = data[i], c = d.counts
                  return (
                    <button key={d.id} onClick={() => openDoc(d.id)} className={`grid gap-0.5 rounded-lg px-2.5 py-2 text-left transition hover:bg-accent ${view === "doc" && cur === d.id ? "bg-accent" : ""}`}>
                      <span className="flex items-center justify-between gap-2">
                        <span className="truncate font-mono text-xs">{d.title.designation || d.file}</span>
                        {d.sheets && <span className="text-[10px] text-muted-foreground">{d.sheets}</span>}
                      </span>
                      <span className="truncate text-xs text-muted-foreground" title={d.file}>{d.title.name || ""}{d.title.name ? " · " : ""}{d.file}</span>
                      <span className="mt-0.5 flex flex-wrap gap-1">
                        {c.error > 0 && <SevBadge sev="error">{c.error}</SevBadge>}
                        {c.warning > 0 && <SevBadge sev="warning">{c.warning}</SevBadge>}
                        {c.info > 0 && <SevBadge sev="info">{c.info}</SevBadge>}
                        {!c.error && !c.warning && <OkBadge />}
                      </span>
                    </button>
                  )
                })}
              </div>
            </ScrollArea>
          </aside>
        )}

        <section className="flex min-h-0 min-w-0 flex-1 flex-col gap-2">
          {view === "comp" && comp ? <CompView comp={comp} onOpen={openDoc} /> : !doc ? (
            <p className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">{job.state === "running" ? "Идёт проверка…" : "Документов нет"}</p>
          ) : (
            <>
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="min-w-0">
                  <h2 className="truncate text-base font-semibold tracking-tight">
                    {doc.title.designation || doc.file} <span className="font-normal text-muted-foreground">{doc.title.name}</span>
                  </h2>
                  <p className="text-xs text-muted-foreground">
                    {summary.join(" · ")}{" "}
                    <button className="text-primary hover:underline" onClick={() => setKvOpen(o => !o)}>{kvOpen ? "скрыть данные" : "все данные"}{kvOpen ? <ChevronUp className="ml-0.5 inline size-3" /> : <ChevronDown className="ml-0.5 inline size-3" />}</button>
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-1.5">
                  {hasViewer && (
                    <Button variant={pick ? "default" : "outline"} size="sm" title="Отметить место на листе, где программа должна была найти ошибку" onClick={() => setPick(p => !p)}>
                      <Target />Программа не заметила
                    </Button>
                  )}
                  <Button variant="outline" size="sm" title="Программа неверно прочитала размер, допуск или штамп" onClick={() => parseDlg("")}><Eye />Неверно прочитано</Button>
                  <Button variant="outline" size="sm" render={<a href={`/api/jobs/${jobId}/remarks.docx?doc=${doc.id}`} />}><FileText />Word</Button>
                  <Counts e={doc.counts.error} w={doc.counts.warning} i={doc.counts.info} />
                </div>
              </div>
              {kvOpen && (
                <div className="grid gap-x-6 gap-y-2 rounded-lg border bg-card p-3 text-sm sm:grid-cols-2 xl:grid-cols-4">
                  {kvOf(doc).map(([k, v]) => <div key={k}><p className="text-xs text-muted-foreground">{k}</p><p className="break-words">{v || "—"}</p></div>)}
                </div>
              )}
              <div className="flex min-h-0 flex-1 flex-col gap-3 lg:flex-row">
                {hasViewer ? (
                  <>
                    <div className="flex min-h-[320px] min-w-0 flex-1">
                      <Viewer ref={viewer} doc={doc} jobId={jobId} findings={findings} selected={selected} onSelect={select} pick={pick} onPick={onPick}
                        missed={docFb.filter(e => e.type === "missed")} />
                    </div>
                    <div onMouseDown={startResize} title="Потяните, чтобы изменить ширину" className="hidden w-1.5 shrink-0 cursor-col-resize rounded bg-border transition hover:bg-primary/50 lg:block" />
                    {panel}
                  </>
                ) : <div className="min-h-0 flex-1 [&>div]:h-full">{panel}</div>}
              </div>
            </>
          )}
        </section>
      </div>
    </div>
  )
}
