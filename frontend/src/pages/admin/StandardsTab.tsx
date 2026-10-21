import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react"
import { ChevronDown, ChevronRight, Copy, Download, FileUp, Search } from "lucide-react"
import { toast } from "sonner"
import { api, errText } from "@/lib/api"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { cn } from "@/lib/utils"
import { Checkbox } from "@/components/ui/checkbox"
import { ClauseTable } from "./ClauseTable"
import { ClausesSheet, MARK_LABEL, type Mark } from "./StandardClauses"

interface Check { status: "ok" | "bad" | "warn" | "scan"; detected: string; note: string }
interface FileInfo { check: Check; id: string; designation: string; pages: number; size: number; has_text: boolean; source: string; same_edition: boolean }
interface Row {
  designation: string; title: string; section: string; file: FileInfo | null; rules: number; codes: string[]; related: number
  reference: boolean; cited_other: string[]; replaced_by: string; catalog_was: string; marks_open: number
}
interface Registry { sections: { key: string; title: string }[]; rows: Row[]; summary: { total: number; loaded: number; needed_missing: number; edition_mismatch: number; check_failed: number; no_checks: number; marks_open: number; stale_refs: number } }
interface UpRes { file: string; ok: boolean; designation?: string; recognized?: boolean; error?: string; check?: Check; corrected?: string }

type Filter = "all" | "missing" | "loaded" | "needed" | "stale" | "nochecks"
const FILTERS: [Filter, string][] = [["all", "Все"], ["needed", "Нужны правилам, PDF нет"], ["missing", "PDF нет"], ["loaded", "PDF есть"], ["nochecks", "PDF есть, проверок нет"], ["stale", "Прежняя редакция в правилах"]]

/** «ГОСТ Р 2.109-2023» → номер «ГОСТ Р 2.109» и год «2023» */
function splitDes(d: string): { num: string; year: string } {
  const m = d.match(/^(.*?)(?:\s*[-–—]\s*(\d{2,4}))?$/)
  return { num: (m?.[1] ?? d).trim(), year: m?.[2] ?? "" }
}

export function StandardsTab() {
  const [reg, setReg] = useState<Registry | null>(null)
  const [err, setErr] = useState("")
  const [filter, setFilter] = useState<Filter>("all")
  const [q, setQ] = useState("")
  const [open, setOpen] = useState<Record<string, boolean>>({})
  const [busy, setBusy] = useState(false)
  const [res, setRes] = useState<UpRes[] | null>(null)
  const bulkRef = useRef<HTMLInputElement>(null)
  const rowRef = useRef<HTMLInputElement>(null)
  const rowDes = useRef("")
  const [sheet, setSheet] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<Record<string, boolean>>({})
  const [marks, setMarks] = useState<Mark[]>([])
  const loadMarks = useCallback(async () => { try { setMarks(await api<Mark[]>("/api/admin/standards/marks")) } catch { setMarks([]) } }, [])
  useEffect(() => { void loadMarks() }, [loadMarks])

  const load = useCallback(async () => {
    try { setReg(await api<Registry>("/api/admin/standards/registry")); setErr("") } catch (e) { setErr(errText(e)) }
  }, [])
  useEffect(() => { void load() }, [load])

  const toggleRef = async (r: Row) => {
    try {
      await api("/api/admin/standards/reference", { json: { designation: r.designation, reference: !r.reference } })
      toast.success(r.reference ? "Отметка «справочный» снята" : "Стандарт отмечен справочным")
      await load()
    } catch (e) { toast.error(errText(e)) }
  }

  const upload = async (files: FileList | File[], designation = "") => {
    const list = Array.from(files)
    if (!list.length) return
    const fd = new FormData()
    list.forEach(f => fd.append("files", f))
    if (designation) fd.append("designation", designation)
    setBusy(true)
    try {
      const j = await api<{ results: UpRes[] }>("/api/admin/standards/upload", { form: fd })
      setRes(j.results)
      const ok = j.results.filter(r => r.ok).length
      if (ok === j.results.length) toast.success(`Загружено: ${ok} из ${j.results.length}`)
      else toast.warning(`Загружено: ${ok} из ${j.results.length}`)
      await load()
    } catch (e) { toast.error(errText(e)) }
    setBusy(false)
    if (bulkRef.current) bulkRef.current.value = ""
    if (rowRef.current) rowRef.current.value = ""
  }

  const match = useCallback((r: Row) => {
    if (filter === "missing" && r.file) return false
    if (filter === "loaded" && !r.file) return false
    if (filter === "needed" && !(r.rules && !r.file)) return false
    if (filter === "nochecks" && !(r.file && !r.rules && !r.reference)) return false
    if (filter === "stale" && !r.cited_other.length) return false
    const s = q.trim().toLowerCase()
    return !s || (r.designation + " " + r.title).toLowerCase().includes(s)
  }, [filter, q])

  const groups = useMemo(() => {
    if (!reg) return []
    return reg.sections.map(s => {
      const rows = reg.rows.filter(r => r.section === s.key)
      return { ...s, rows, shown: rows.filter(match), have: rows.filter(r => r.file).length }
    }).filter(g => g.rows.length)
  }, [reg, match])

  const copyMissing = async () => {
    if (!reg) return
    const lines = reg.rows.filter(r => !r.file).filter(match).map(r => `${r.designation}${r.title ? " — " + r.title : ""}${r.rules ? ` (проверок: ${r.rules})` : ""}`)
    try { await navigator.clipboard.writeText(lines.join("\n")); toast.success(`Скопировано стандартов: ${lines.length}`) } catch { toast.error("Не удалось скопировать") }
  }

  const sm = reg?.summary
  const forced = q.trim() !== "" || filter !== "all"
  const cards: [string, number, string][] = sm ? [
    ["В перечне", sm.total, ""],
    ["PDF загружен", sm.loaded, ""],
    ["Нужны правилам, PDF нет", sm.needed_missing, sm.needed_missing ? "text-destructive" : ""],
    ["Прежняя редакция в правилах", sm.stale_refs, sm.stale_refs ? "text-amber-600" : ""],
    ["PDF есть, проверок нет", sm.no_checks, sm.no_checks ? "text-amber-600" : ""],
    ["Файл не совпал с названием", sm.check_failed, sm.check_failed ? "text-destructive" : ""],
  ] : []
  return (
    <Card>
      <CardHeader>
        <CardTitle>Реестр стандартов</CardTitle>
        <CardDescription>
          Справочный перечень стандартов на конструкторскую и технологическую документацию и состояние каждого: загружен ли PDF и сколько проверок на него ссылается.
          Перечень составлен вручную, это не выгрузка из официального реестра: обозначения и годы сверяйте с действующими изданиями.
          Чтобы добавить стандарт, перетащите PDF в рамку ниже (обозначение определяется по имени файла или первой странице) либо нажмите «Загрузить» в строке стандарта.
          Загруженные файлы попадают во вкладку «Нормативы» и используются для ссылок на пункты и поиска по тексту.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4">
        {sm && (
          <div className="grid grid-cols-2 gap-2 md:grid-cols-3 xl:grid-cols-6">
            {cards.map(([t, n, c]) => (
              <div key={t} className="rounded-lg border p-3"><div className={cn("text-2xl font-semibold", c)}>{n}</div><div className="text-xs text-muted-foreground">{t}</div></div>
            ))}
          </div>
        )}

        <div
          className="flex flex-wrap items-center justify-start gap-3 rounded-lg border-2 border-dashed p-4 text-left text-sm text-muted-foreground"
          onDragOver={e => e.preventDefault()}
          onDrop={e => { e.preventDefault(); void upload(e.dataTransfer.files) }}
        >
          <input ref={bulkRef} type="file" multiple accept=".pdf,application/pdf" className="hidden" onChange={e => { if (e.target.files) void upload(e.target.files) }} />
          <Button variant="outline" disabled={busy} onClick={() => bulkRef.current?.click()}><FileUp />{busy ? "Загрузка…" : "Выбрать файлы"}</Button>
          <span>или перетащите сюда PDF стандартов (можно сразу много)</span>
        </div>
        {res && (
          <div className="rounded-lg border p-3 text-sm">
            <div className="mb-1 font-medium">Результат загрузки</div>
            {res.map((r, i) => (
              <div key={i} className={r.ok ? "" : "text-destructive"}>
                {r.file} — {r.ok ? (r.recognized ? `распознан как ${r.designation}` : "обозначение не распознано, добавлено по имени файла; уточните во вкладке «Нормативы»") : r.error}
                {r.corrected && <span className="text-emerald-600"> · обозначение исправлено по тексту файла: {r.designation}</span>}
                {r.check && r.check.status !== "ok" && <span className={r.check.status === "bad" ? "font-medium text-destructive" : "text-amber-600"}> · {r.check.note}</span>}
              </div>
            ))}
          </div>
        )}
        <input ref={rowRef} type="file" accept=".pdf,application/pdf" className="hidden" onChange={e => { if (e.target.files) void upload(e.target.files, rowDes.current) }} />

        {marks.some(m => m.status === "open") && (
          <div className="rounded-lg border border-amber-500/50 bg-amber-500/5 p-3 text-sm">
            <div className="mb-1 font-medium">Заявки на проверки ({marks.filter(m => m.status === "open").length})</div>
            {marks.filter(m => m.status === "open").map(m => (
              <div key={m.id} className="flex flex-wrap items-center gap-2 py-0.5">
                <button type="button" className="font-medium text-primary hover:underline" onClick={() => setSheet(m.file_id)}>{m.std} п. {m.clause}</button>
                <span className="flex-1 text-muted-foreground">{m.comment || m.text.slice(0, 90)}</span>
                <Badge variant="secondary">{MARK_LABEL[m.status]}</Badge>
              </div>
            ))}
          </div>
        )}

        <div className="flex flex-wrap items-center gap-2">
          <div className="relative"><Search className="pointer-events-none absolute left-2.5 top-2.5 size-4 text-muted-foreground" />
            <Input className="w-80 pl-8" placeholder="Обозначение или название" value={q} onChange={e => setQ(e.target.value)} /></div>
          {FILTERS.map(([k, t]) => <Button key={k} size="sm" variant={filter === k ? "default" : "outline"} onClick={() => setFilter(k)}>{t}</Button>)}
          <Button size="sm" variant="ghost" onClick={() => void copyMissing()} title="Копирует список стандартов без PDF по текущему фильтру"><Copy />Скопировать список без PDF</Button>
        </div>
        {err && <p className="text-sm text-destructive">{err}</p>}
        {!reg && !err && <p className="text-sm text-muted-foreground">Загрузка…</p>}

        {reg && (
          <div className="overflow-auto rounded-lg border">
            <Table>
              <TableHeader className="sticky top-0 z-10 bg-muted">
                <TableRow>
                  <TableHead className="w-8" />
                  <TableHead className="w-40">Стандарт</TableHead>
                  <TableHead className="w-16">Год</TableHead>
                  <TableHead>Название</TableHead>
                  <TableHead className="w-40">PDF</TableHead>
                  <TableHead className="w-24 text-center" title="Справочный стандарт: проверок по нему не планируется">Справочный</TableHead>
                  <TableHead className="w-24 text-center" title="Сколько проверок ссылается на стандарт">Проверок</TableHead>
                  <TableHead className="w-24 text-center" title="Заявки на проверки по пунктам">Заявок</TableHead>
                  <TableHead className="w-36" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {groups.map(g => {
                  if (forced && !g.shown.length) return null
                  const isOpen = forced ? true : !!open[g.key]
                  return (
                    <Fragment key={g.key}>
                      <TableRow className="cursor-pointer bg-muted/50 hover:bg-muted/70" onClick={() => setOpen(o => ({ ...o, [g.key]: !o[g.key] }))}>
                        <TableCell colSpan={9} className="font-medium">
                          <span className="flex items-center gap-2">
                            {isOpen ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}
                            <span className="flex-1">{g.title}</span>
                            <span className="text-xs font-normal text-muted-foreground">PDF: {g.have} из {g.rows.length}</span>
                          </span>
                        </TableCell>
                      </TableRow>
                      {isOpen && g.shown.map(r => {
                        const { num, year } = splitDes(r.designation)
                        const fid = r.file?.id
                        const ex = !!(fid && expanded[fid])
                        return (
                          <Fragment key={r.designation + "|" + (fid ?? "")}>
                            <TableRow className={cn(r.reference && "text-muted-foreground")}>
                              <TableCell className="px-1">
                                {fid && <Button variant="ghost" size="icon-xs" aria-label={ex ? "Свернуть пункты" : "Показать пункты"} onClick={() => setExpanded(e => ({ ...e, [fid]: !e[fid] }))}>
                                  {ex ? <ChevronDown /> : <ChevronRight />}</Button>}
                              </TableCell>
                              <TableCell className="whitespace-nowrap font-medium">{num}</TableCell>
                              <TableCell className="whitespace-nowrap">{year || <span className="text-muted-foreground">—</span>}</TableCell>
                              <TableCell className="whitespace-normal">
                                <div className="text-sm">{r.title}</div>
                                {r.catalog_was && <div className="text-xs text-emerald-600">загружена редакция новее, чем в перечне ({r.catalog_was})</div>}
                                {r.replaced_by && <div className="text-xs text-amber-600">заменён на {r.replaced_by}</div>}
                                {r.cited_other.length > 0 && <div className="text-xs text-amber-600">правила ссылаются на: {r.cited_other.join(", ")}</div>}
                              </TableCell>
                              <TableCell className="whitespace-normal">
                                {r.file
                                  ? <div className="grid gap-0.5"><Badge>загружен</Badge>
                                    {r.file.check.status === "bad" && <Badge variant="destructive">не тот документ?</Badge>}
                                    {r.file.check.status === "warn" && <Badge variant="secondary">проверьте название</Badge>}
                                    {r.file.check.status !== "ok" && <span className={cn("text-xs", r.file.check.status === "bad" ? "text-destructive" : "text-amber-600")}>{r.file.check.note}</span>}
                                    <span className="text-xs text-muted-foreground">{r.file.pages} стр.{!r.file.has_text && ", скан без текста"}{!r.file.same_edition && `, файл: ${r.file.designation}`}</span></div>
                                  : <Badge variant={r.rules ? "destructive" : "secondary"}>{r.rules ? "нужен правилам" : "нет"}</Badge>}
                              </TableCell>
                              <TableCell className="text-center">
                                <Checkbox checked={r.reference} onCheckedChange={() => void toggleRef(r)} aria-label={`${r.designation}: справочный`} />
                              </TableCell>
                              <TableCell className="text-center" title={r.codes.join(", ")}>{r.rules ? <span>{r.rules}{r.related ? <span className="text-muted-foreground"> (+{r.related})</span> : null}</span> : <span className="text-muted-foreground">—</span>}</TableCell>
                              <TableCell className="text-center">{r.marks_open > 0 ? <Badge>{r.marks_open}</Badge> : <span className="text-muted-foreground">—</span>}</TableCell>
                              <TableCell><div className="flex justify-end gap-1">
                                {r.file && <Button variant="ghost" size="icon-xs" title="Открыть PDF" aria-label="Открыть PDF" render={<a href={"/norms/" + encodeURIComponent(r.file.id)} target="_blank" rel="noreferrer" />}><Download /></Button>}
                                <Button variant="ghost" size="sm" disabled={busy} onClick={() => { rowDes.current = r.designation; rowRef.current?.click() }}><FileUp />{r.file ? "Заменить" : "Загрузить"}</Button>
                              </div></TableCell>
                            </TableRow>
                            {ex && fid && (
                              <TableRow className="bg-muted/20 hover:bg-muted/20">
                                <TableCell />
                                <TableCell colSpan={8} className="whitespace-normal p-0">
                                  <ClauseTable fileId={fid} designation={r.designation} onChanged={() => { void load(); void loadMarks() }} onCollapse={() => setExpanded(e => ({ ...e, [fid]: false }))} />
                                </TableCell>
                              </TableRow>
                            )}
                          </Fragment>
                        )
                      })}
                    </Fragment>
                  )
                })}
              </TableBody>
            </Table>
          </div>
        )}
        <ClausesSheet fileId={sheet} onClose={() => setSheet(null)} onChanged={() => { void load(); void loadMarks() }} />
      </CardContent>
    </Card>
  )
}
