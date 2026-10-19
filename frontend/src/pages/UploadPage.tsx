import { useCallback, useEffect, useRef, useState } from "react"
import { useNavigate } from "react-router-dom"
import { Clock, Cpu, FileText, FolderOpen, PlayCircle, ScanText, UploadCloud, X } from "lucide-react"
import { api, errText } from "@/lib/api"
import { jobWhen } from "@/lib/format"
import type { HistoryItem } from "@/lib/types"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import { Progress } from "@/components/ui/progress"
import { Badge } from "@/components/ui/badge"

type PFile = File & { relPath?: string }
const fkey = (f: File) => `${f.name}|${f.size}|${f.lastModified}`

async function walk(entry: any, path: string): Promise<PFile[]> {
  if (entry.isFile) {
    return new Promise(res => entry.file((f: PFile) => { f.relPath = path + f.name; res([f]) }, () => res([])))
  }
  if (entry.isDirectory) {
    const reader = entry.createReader()
    let all: PFile[] = []
    for (;;) {
      const batch: any[] = await new Promise(res => reader.readEntries(res, () => res([])))
      if (!batch.length) break
      for (const e of batch) all = all.concat(await walk(e, path + entry.name + "/"))
    }
    return all
  }
  return []
}

function FileList({ list, onRemove }: { list: PFile[]; onRemove: (i: number) => void }) {
  if (!list.length) return null
  return (
    <ul className="max-h-56 divide-y overflow-auto rounded-lg border">
      {list.map((f, i) => (
        <li key={fkey(f)} className="flex items-center gap-3 px-3 py-1.5 text-sm">
          <FileText className="size-4 shrink-0 text-muted-foreground" />
          <span className="min-w-0 flex-1 truncate">{f.relPath || (f as any).webkitRelativePath || f.name}</span>
          <span className="text-xs text-muted-foreground">{(f.size / 1024).toFixed(0)} КБ</span>
          <Button variant="ghost" size="icon-xs" aria-label="Убрать" onClick={() => onRemove(i)}><X /></Button>
        </li>
      ))}
    </ul>
  )
}

function Step({ n, title, hint, children }: { n: number; title: React.ReactNode; hint?: React.ReactNode; children: React.ReactNode }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <span className="grid size-6 place-items-center rounded-full bg-primary text-xs font-semibold text-primary-foreground">{n}</span>{title}
        </CardTitle>
        {hint && <CardDescription>{hint}</CardDescription>}
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  )
}

export default function UploadPage() {
  const nav = useNavigate()
  const [picked, setPicked] = useState<PFile[]>([])
  const [specs, setSpecs] = useState<PFile[]>([])
  const [procs, setProcs] = useState<PFile[]>([])
  const [folder, setFolder] = useState("")
  const [ocr, setOcr] = useState(true)
  const [over, setOver] = useState(false)
  const [note, setNote] = useState("")
  const [running, setRunning] = useState(false)
  const [prog, setProg] = useState({ done: 0, total: 0, text: "" })
  const [err, setErr] = useState("")
  const [hist, setHist] = useState<HistoryItem[] | null>(null)
  const inp = useRef<HTMLInputElement>(null)
  const specInp = useRef<HTMLInputElement>(null)
  const procInp = useRef<HTMLInputElement>(null)
  const alive = useRef(true)

  useEffect(() => { alive.current = true; return () => { alive.current = false } }, [])
  useEffect(() => { api<HistoryItem[]>("/api/history").then(setHist).catch(() => setHist([])) }, [])

  // один и тот же файл (имя, размер, дата изменения) в проверку добавляется один раз — во всех трёх списках
  const add = useCallback((set: React.Dispatch<React.SetStateAction<PFile[]>>, files: PFile[]) => {
    const skipped: string[] = []
    const seen = new Set([...picked, ...specs, ...procs].map(fkey))
    const fresh: PFile[] = []
    for (const f of files) {
      if (seen.has(fkey(f))) skipped.push(f.name)
      else { seen.add(fkey(f)); fresh.push(f) }
    }
    setNote(skipped.length ? "Пропущен дубликат: " + [...new Set(skipped)].join(", ") : "")
    if (fresh.length) set(l => [...l, ...fresh])
  }, [picked, specs, procs])

  const onDrop = async (ev: React.DragEvent) => {
    ev.preventDefault()
    setOver(false)
    const items = [...(ev.dataTransfer.items || [])]
    if (items.length && (items[0] as any).webkitGetAsEntry) {
      let all: PFile[] = []
      for (const it of items) { const e = (it as any).webkitGetAsEntry(); if (e) all = all.concat(await walk(e, "")) }
      add(setPicked, all)
    } else add(setPicked, [...ev.dataTransfer.files])
  }

  const poll = async (id: string) => {
    try {
      const j = await api<any>(`/api/jobs/${id}`)
      if (!alive.current) return
      setProg({ done: j.done, total: j.total, text: j.current || "" })
      if (j.state === "done") { nav(`/job/${id}`); return }
      if (j.state === "error") { setErr(j.error); setRunning(false); return }
      setTimeout(() => poll(id), 700)
    } catch (e) { setErr(errText(e)); setRunning(false) }
  }

  const go = async () => {
    setErr("")
    const fd = new FormData()
    picked.forEach(f => fd.append("files", f, f.name))
    fd.append("folder", folder)
    specs.forEach(f => fd.append("spec", f, f.name))
    procs.forEach(f => fd.append("process", f, f.name))
    fd.append("ocr", ocr ? "1" : "0")
    setRunning(true)
    setProg({ done: 0, total: 0, text: "Загрузка файлов…" })
    try {
      const j = await api<{ job_id: string }>("/api/jobs", { form: fd })
      void poll(j.job_id)
    } catch (e) { setErr(errText(e)); setRunning(false) }
  }

  const pct = prog.total ? Math.round((100 * prog.done) / prog.total) : 0
  const nothing = !picked.length && !folder.trim()

  return (
    <div className="mx-auto grid max-w-6xl gap-4 p-4 md:p-6 lg:grid-cols-[1fr_340px]">
      <div className="grid content-start gap-4">
        <Step n={1} title="Чертежи" hint="PDF (векторные и сканы), PNG/JPG/TIF, ZIP-архив. DXF-развёртки кладите сюда же — сверятся с чертежами.">
          <div className="grid gap-4">
            <div
              role="button" tabIndex={0}
              onClick={() => inp.current?.click()}
              onKeyDown={e => { if (e.key === "Enter") inp.current?.click() }}
              onDragEnter={e => { e.preventDefault(); setOver(true) }}
              onDragOver={e => { e.preventDefault(); setOver(true) }}
              onDragLeave={() => setOver(false)}
              onDrop={onDrop}
              className={`group flex cursor-pointer flex-col items-center gap-2 rounded-xl border-2 border-dashed px-6 py-10 text-center transition hover:border-primary hover:bg-primary/5 ${over ? "border-primary bg-primary/5" : "bg-muted/40"}`}
            >
              <div className="grid size-12 place-items-center rounded-full bg-primary/10 text-primary transition group-hover:scale-105"><UploadCloud className="size-6" /></div>
              <p className="font-medium">Перетащите файлы или папку сюда</p>
              <p className="text-sm text-muted-foreground">или нажмите, чтобы выбрать</p>
            </div>
            <input ref={inp} type="file" multiple hidden accept=".pdf,.dxf,.png,.jpg,.jpeg,.tif,.tiff,.bmp,.zip"
              onChange={e => { add(setPicked, [...(e.target.files ?? [])]); e.target.value = "" }} />
            <FileList list={picked} onRemove={i => setPicked(l => l.filter((_, j) => j !== i))} />
            {note && <p className="text-xs text-[var(--sev-warn)]">{note}</p>}
            <div className="grid gap-2">
              <Label htmlFor="folder" className="flex items-center gap-1.5"><FolderOpen className="size-4" />…или путь к папке на этом компьютере</Label>
              <Input id="folder" value={folder} onChange={e => setFolder(e.target.value)} placeholder="D:\КД\Опора пассивная" />
              <p className="text-xs text-muted-foreground">Проверяются все чертежи в папке и подпапках, файлы никуда не копируются.</p>
            </div>
          </div>
        </Step>

        <Step n={2} title={<>Спецификации <span className="text-sm font-normal text-muted-foreground">(необязательно)</span></>}
          hint="Спецификация в PDF (по форме 1 ГОСТ 2.106) прикладывается вместе со сборочным чертежом: программа найдёт его по обозначению, сверит номера позиций, наименования и составные части, а саму таблицу проверит по ГОСТ 2.106. Excel (СП из ERP, табличный экспорт): сверяются масса, наименование, материал, марка и толщина, количество, строится комплектность.">
          <div className="grid gap-3">
            <div><Button variant="outline" onClick={() => specInp.current?.click()}><UploadCloud />Добавить спецификации</Button></div>
            <input ref={specInp} type="file" multiple hidden accept=".xlsx,.xlsm,.xls,.pdf"
              onChange={e => { add(setSpecs, [...(e.target.files ?? [])]); e.target.value = "" }} />
            <FileList list={specs} onRemove={i => setSpecs(l => l.filter((_, j) => j !== i))} />
          </div>
        </Step>

        <Step n={3} title={<>Маршрутные карты и техпроцессы <span className="text-sm font-normal text-muted-foreground">(необязательно)</span></>}
          hint="PDF (текст или скан), Excel, Word. Программа определяет вид документа, обозначение детали и список операций и связывает документ с чертежом. Правил проверки технологии пока нет — документы показываются в отчёте.">
          <div className="grid gap-3">
            <div><Button variant="outline" onClick={() => procInp.current?.click()}><Cpu />Добавить техпроцессы</Button></div>
            <input ref={procInp} type="file" multiple hidden accept=".pdf,.xlsx,.xlsm,.xls,.docx"
              onChange={e => { add(setProcs, [...(e.target.files ?? [])]); e.target.value = "" }} />
            <FileList list={procs} onRemove={i => setProcs(l => l.filter((_, j) => j !== i))} />
          </div>
        </Step>

        <Card>
          <CardContent className="grid gap-4 pt-6">
            <div className="flex items-center justify-between gap-4">
              <div className="flex items-center gap-3">
                <ScanText className="size-5 text-muted-foreground" />
                <div>
                  <Label htmlFor="ocr">Распознавать сканы (OCR, локально)</Label>
                  <p className="text-xs text-muted-foreground">Около 10 с на лист. Без интернета и внешних сервисов.</p>
                </div>
              </div>
              <Switch id="ocr" checked={ocr} onCheckedChange={setOcr} />
            </div>
            {running && (
              <div className="grid gap-2">
                <Progress value={pct} />
                <p className="break-words text-sm text-muted-foreground">
                  {prog.total ? `Проверено ${prog.done} из ${prog.total}` : ""}{prog.text ? ` · ${prog.text}` : ""}
                </p>
              </div>
            )}
            {err && <pre className="max-h-48 overflow-auto whitespace-pre-wrap rounded-md border border-[var(--sev-error)]/30 bg-[var(--sev-error-bg)] p-3 text-xs text-[var(--sev-error)]">{err}</pre>}
            <Button size="lg" onClick={go} disabled={running || nothing} className="w-full sm:w-fit">
              <PlayCircle />Проверить{picked.length ? ` (файлов: ${picked.length})` : ""}
            </Button>
          </CardContent>
        </Card>
      </div>

      <Card className="h-fit">
        <CardHeader><CardTitle className="flex items-center gap-2"><Clock className="size-4" />Последние проверки</CardTitle></CardHeader>
        <CardContent className="grid gap-1">
          {hist === null && <p className="text-sm text-muted-foreground">Загрузка…</p>}
          {hist?.length === 0 && <p className="text-sm text-muted-foreground">Пока нет</p>}
          {hist?.slice(0, 12).map(h => (
            <button key={h.id} onClick={() => nav(`/job/${h.id}`)} className="grid gap-1 rounded-lg px-2 py-2 text-left transition hover:bg-accent">
              <span className="flex items-center justify-between gap-2 text-sm">
                <span>{jobWhen(h.id)} · {h.count} док.</span>
                <span className="flex gap-1">
                  <Badge variant="secondary" className="text-[var(--sev-error)]">{h.errors}</Badge>
                  <Badge variant="secondary" className="text-[var(--sev-warn)]">{h.warnings}</Badge>
                </span>
              </span>
              {h.owner && <span className="text-xs text-muted-foreground">{h.owner}</span>}
            </button>
          ))}
        </CardContent>
      </Card>
    </div>
  )
}
