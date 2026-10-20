import { useCallback, useEffect, useRef, useState } from "react"
import { useNavigate } from "react-router-dom"
import { Clock, FileText, FolderOpen, PlayCircle, ScanText, UploadCloud, X } from "lucide-react"
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
const ACCEPT = ".pdf,.dxf,.png,.jpg,.jpeg,.tif,.tiff,.bmp,.zip,.xlsx,.xlsm,.xls,.docx"

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

/** Предварительная подсказка по расширению; точный вид документа программа определяет при проверке. */
function hint(f: File): string {
  const ext = f.name.slice(f.name.lastIndexOf(".")).toLowerCase()
  if ([".xlsx", ".xlsm", ".xls"].includes(ext)) return "Excel: спецификация или техпроцесс"
  if (ext === ".docx") return "техпроцесс (Word)"
  if (ext === ".zip") return "архив"
  if (ext === ".dxf") return "DXF-развёртка"
  if (ext === ".pdf") return "чертёж, спецификация или МК"
  return "чертёж (изображение)"
}

function FileList({ list, onRemove }: { list: PFile[]; onRemove: (i: number) => void }) {
  if (!list.length) return null
  return (
    <ul className="max-h-72 divide-y overflow-auto rounded-lg border">
      {list.map((f, i) => (
        <li key={fkey(f)} className="flex items-center gap-3 px-3 py-1.5 text-sm">
          <FileText className="size-4 shrink-0 text-muted-foreground" />
          <span className="min-w-0 flex-1 truncate">{f.relPath || (f as any).webkitRelativePath || f.name}</span>
          <span className="hidden text-xs text-muted-foreground sm:inline">{hint(f)}</span>
          <span className="text-xs text-muted-foreground">{(f.size / 1024).toFixed(0)} КБ</span>
          <Button variant="ghost" size="icon-xs" aria-label="Убрать" onClick={() => onRemove(i)}><X /></Button>
        </li>
      ))}
    </ul>
  )
}

export default function UploadPage() {
  const nav = useNavigate()
  const [picked, setPicked] = useState<PFile[]>([])
  const [folder, setFolder] = useState("")
  const [ocr, setOcr] = useState(true)
  const [over, setOver] = useState(false)
  const [note, setNote] = useState("")
  const [running, setRunning] = useState(false)
  const [prog, setProg] = useState({ done: 0, total: 0, text: "" })
  const [err, setErr] = useState("")
  const [hist, setHist] = useState<HistoryItem[] | null>(null)
  const inp = useRef<HTMLInputElement>(null)
  const alive = useRef(true)

  useEffect(() => { alive.current = true; return () => { alive.current = false } }, [])
  useEffect(() => { api<HistoryItem[]>("/api/history").then(setHist).catch(() => setHist([])) }, [])

  // один и тот же файл (имя, размер, дата изменения) в проверку добавляется один раз
  const add = useCallback((files: PFile[]) => {
    const skipped: string[] = []
    const seen = new Set(picked.map(fkey))
    const fresh: PFile[] = []
    for (const f of files) {
      if (seen.has(fkey(f))) skipped.push(f.name)
      else { seen.add(fkey(f)); fresh.push(f) }
    }
    setNote(skipped.length ? "Пропущен дубликат: " + [...new Set(skipped)].join(", ") : "")
    if (fresh.length) setPicked(l => [...l, ...fresh])
  }, [picked])

  const onDrop = async (ev: React.DragEvent) => {
    ev.preventDefault()
    setOver(false)
    const items = [...(ev.dataTransfer.items || [])]
    if (items.length && (items[0] as any).webkitGetAsEntry) {
      let all: PFile[] = []
      for (const it of items) { const e = (it as any).webkitGetAsEntry(); if (e) all = all.concat(await walk(e, "")) }
      add(all)
    } else add([...ev.dataTransfer.files])
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
    picked.forEach(f => fd.append("docs", f, f.name))           // вид каждого файла определяет программа
    fd.append("folder", folder)
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
        <Card className="sticky top-0 z-10 shadow-sm">
          <CardContent className="grid gap-3 pt-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="min-w-0">
                <h1 className="text-base font-semibold">Новая проверка</h1>
                <p className="text-xs text-muted-foreground">
                  {picked.length || folder.trim() ? `Файлов: ${picked.length}${folder.trim() ? " + папка" : ""}` : "Добавьте файлы или укажите папку"}
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-4">
                <div className="flex items-center gap-2">
                  <ScanText className="size-4 text-muted-foreground" />
                  <Label htmlFor="ocr" className="text-sm font-normal" title="Около 10 с на лист. Без интернета и внешних сервисов.">Распознавать сканы</Label>
                  <Switch id="ocr" checked={ocr} onCheckedChange={setOcr} />
                </div>
                <Button size="lg" onClick={go} disabled={running || nothing}><PlayCircle />Проверить</Button>
              </div>
            </div>
            {running && (
              <div className="grid gap-1.5">
                <Progress value={pct} />
                <p className="break-words text-sm text-muted-foreground">
                  {prog.total ? `Проверено ${prog.done} из ${prog.total}` : ""}{prog.text ? ` · ${prog.text}` : ""}
                </p>
              </div>
            )}
            {err && <pre className="max-h-48 overflow-auto whitespace-pre-wrap rounded-md border border-[var(--sev-error)]/30 bg-[var(--sev-error-bg)] p-3 text-xs text-[var(--sev-error)]">{err}</pre>}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Документы</CardTitle>
            <CardDescription>
              Кладите всё в одно место: чертежи (PDF — векторные и сканы, PNG/JPG/TIF, DXF-развёртки, ZIP-архивы), спецификации (Excel или PDF по форме 1 ГОСТ 2.106),
              маршрутные карты и техпроцессы (PDF, Excel, Word). Вид каждого файла программа определяет сама и связывает документы по обозначению.
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4">
            <div
              role="button" tabIndex={0}
              onClick={() => inp.current?.click()}
              onKeyDown={e => { if (e.key === "Enter") inp.current?.click() }}
              onDragEnter={e => { e.preventDefault(); setOver(true) }}
              onDragOver={e => { e.preventDefault(); setOver(true) }}
              onDragLeave={() => setOver(false)}
              onDrop={onDrop}
              className={`group flex cursor-pointer flex-col items-center gap-2 rounded-xl border-2 border-dashed px-6 py-10 text-center transition hover:border-primary hover:bg-primary/5 ${over ? "border-primary bg-primary/5" : ""}`}
            >
              <div className="grid size-12 place-items-center rounded-full bg-primary/10 text-primary transition group-hover:scale-105"><UploadCloud className="size-6" /></div>
              <p className="font-medium">Перетащите файлы или папку сюда</p>
              <p className="text-sm text-muted-foreground">или нажмите, чтобы выбрать</p>
            </div>
            <input ref={inp} type="file" multiple hidden accept={ACCEPT}
              onChange={e => { add([...(e.target.files ?? [])]); e.target.value = "" }} />
            <FileList list={picked} onRemove={i => setPicked(l => l.filter((_, j) => j !== i))} />
            {note && <p className="text-xs text-[var(--sev-warn)]">{note}</p>}
            <div className="grid gap-2">
              <Label htmlFor="folder" className="flex items-center gap-1.5"><FolderOpen className="size-4" />…или путь к папке на этом компьютере</Label>
              <Input id="folder" value={folder} onChange={e => setFolder(e.target.value)} placeholder="D:\КД\Опора пассивная" />
              <p className="text-xs text-muted-foreground">Проверяются все чертежи в папке и подпапках, файлы никуда не копируются.</p>
            </div>
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
