import { useCallback, useEffect, useMemo, useState } from "react"
import { ExternalLink, Flag, HelpCircle, Search, Trash2 } from "lucide-react"
import { toast } from "sonner"
import { api, errText } from "@/lib/api"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet"
import { Textarea } from "@/components/ui/textarea"
import { cn } from "@/lib/utils"

export interface Mark { id: string; file_id: string; std: string; clause: string; text: string; comment: string; status: "open" | "done" | "rejected"; code: string; author: string; created: string }
interface RuleDoc { what?: string; how?: string; example?: string; skip?: string; params?: string }
interface CodeInfo { text: string; sev: string; default: boolean; link: "exact" | "indirect" | "unreviewed"; link_note: string; doc: RuleDoc | null; rev: number }
interface Clause { n: string; page: number; text: string; checks: string[]; child_checks: string[]; marks: Mark[] }
interface Detail { id: string; designation: string; title: string; pages: number; clauses: Clause[]; whole: string[]; codes: Record<string, CodeInfo>; stale: string[]; marks_without_clause: Mark[] }

export const MARK_LABEL: Record<Mark["status"], string> = { open: "ждёт проверки", done: "проверка сделана", rejected: "отклонена" }
const LINK_TXT = { exact: "связь подтверждена текстом стандарта", indirect: "связь косвенная", unreviewed: "связь не сверена" } as const
const SEV: Record<string, string> = { error: "ошибка", warning: "предупреждение", info: "информация" }

type View = "all" | "none" | "checked" | "marked"

export function ClausesSheet({ fileId, onClose, onChanged }: { fileId: string | null; onClose: () => void; onChanged: () => void }) {
  const [d, setD] = useState<Detail | null>(null)
  const [err, setErr] = useState("")
  const [q, setQ] = useState("")
  const [view, setView] = useState<View>("all")
  const [editing, setEditing] = useState<string | null>(null)
  const [comment, setComment] = useState("")
  const [open, setOpen] = useState<{ n: string; code: string } | null>(null)
  const [full, setFull] = useState<Record<string, boolean>>({})
  const [help, setHelp] = useState(false)

  const load = useCallback(async () => {
    if (!fileId) return
    try { setD(await api<Detail>("/api/admin/standards/detail?id=" + encodeURIComponent(fileId))); setErr("") } catch (e) { setErr(errText(e)) }
  }, [fileId])
  useEffect(() => { setD(null); setQ(""); setView("all"); setEditing(null); setOpen(null); setFull({}); void load() }, [load])

  const shown = useMemo(() => {
    if (!d) return []
    const s = q.trim().toLowerCase()
    return d.clauses.filter(c => {
      if (view === "none" && (c.checks.length || c.child_checks.length)) return false
      if (view === "checked" && !c.checks.length) return false
      if (view === "marked" && !c.marks.length) return false
      return !s || (c.n + " " + c.text).toLowerCase().includes(s)
    })
  }, [d, q, view])

  const mark = async (c: Clause) => {
    if (!d) return
    try {
      await api("/api/admin/standards/marks", { json: { file_id: d.id, clause: c.n, text: c.text, comment } })
      toast.success(`Пункт ${c.n} отмечен: по нему нужна проверка`)
      setEditing(null); setComment(""); await load(); onChanged()
    } catch (e) { toast.error(errText(e)) }
  }
  const setStatus = async (m: Mark, status: Mark["status"]) => {
    try { await api("/api/admin/standards/marks/" + m.id, { method: "PATCH", json: { status } }); await load(); onChanged() } catch (e) { toast.error(errText(e)) }
  }
  const remove = async (m: Mark) => {
    try { await api("/api/admin/standards/marks/" + m.id, { method: "DELETE" }); await load(); onChanged() } catch (e) { toast.error(errText(e)) }
  }

  const chips = (c: Clause, codes: string[], dim = false) => codes.map(code => {
    const info = d?.codes[code]
    const lv = info?.link ?? "unreviewed"
    const active = open?.n === c.n && open.code === code
    return (
      <button key={code} type="button" onClick={() => setOpen(active ? null : { n: c.n, code })} title="Показать проверку рядом с текстом пункта">
        <Badge variant={active ? "default" : dim ? "outline" : "secondary"}
          className={cn("cursor-pointer", lv === "indirect" && !active && "border border-dashed border-amber-500 text-amber-700", lv === "unreviewed" && !active && "border border-dotted opacity-70")}>
          {code}{lv === "indirect" ? "~" : lv === "unreviewed" ? "?" : ""}
        </Badge>
      </button>
    )
  })
  const nChecked = d ? d.clauses.filter(c => c.checks.length).length : 0

  const sideBySide = (c: Clause, code: string) => {
    const info = d?.codes[code]
    const doc = info?.doc
    const lv = info?.link ?? "unreviewed"
    return (
      <div className="mt-2 grid gap-3 rounded-md border bg-muted/30 p-3 text-sm md:grid-cols-2">
        <div>
          <div className="mb-1 text-xs font-medium uppercase text-muted-foreground">Пункт {c.n} стандарта (стр. {c.page})</div>
          <p className="whitespace-pre-wrap">{c.text || "—"}</p>
          <Button variant="link" size="sm" className="h-auto p-0" render={<a href={`/norms/${encodeURIComponent(d!.id)}#page=${c.page}`} target="_blank" rel="noreferrer" />}>Открыть PDF на этой странице</Button>
        </div>
        <div>
          <div className="mb-1 text-xs font-medium uppercase text-muted-foreground">Проверка {code}{info ? ` · ${SEV[info.sev] ?? info.sev} · версия ${info.rev}${info.default ? "" : " · выключена по умолчанию"}` : ""}</div>
          <p className="font-medium">{info?.text}</p>
          {doc?.what && <p className="mt-1"><b>Что проверяет: </b>{doc.what}</p>}
          {doc?.how && <p className="mt-1"><b>Как: </b>{doc.how}</p>}
          {doc?.example && <p className="mt-1"><b>Пример замечания: </b>{doc.example}</p>}
          {doc?.skip && <p className="mt-1"><b>Когда не срабатывает: </b>{doc.skip}</p>}
          {!doc && <p className="mt-1 text-muted-foreground">Описания у этой проверки нет.</p>}
          <p className={cn("mt-2 text-xs", lv === "exact" ? "text-emerald-600" : lv === "indirect" ? "text-amber-600" : "text-muted-foreground")}>
            {LINK_TXT[lv]}{info?.link_note ? `: ${info.link_note}` : ""}
          </p>
          <p className="mt-1 text-xs text-muted-foreground">Если проверка не соответствует тексту пункта, нажмите «Отметить» у пункта и опишите, что нужно изменить.</p>
        </div>
      </div>
    )
  }

  return (
    <Sheet open={!!fileId} onOpenChange={o => { if (!o) onClose() }}>
      <SheetContent side="right" className="w-full gap-3 overflow-y-auto p-4 data-[side=right]:sm:max-w-4xl">
        <SheetHeader className="p-0">
          <SheetTitle>{d?.designation ?? "Пункты стандарта"}</SheetTitle>
          <SheetDescription>{d?.title}</SheetDescription>
        </SheetHeader>
        {err && <p className="text-sm text-destructive">{err}</p>}
        {!d && !err && <p className="text-sm text-muted-foreground">Загрузка…</p>}
        {d && (
          <>
            <div className="text-sm text-muted-foreground">
              Пунктов найдено: {d.clauses.length}; на {nChecked} из них есть проверки.
              <button type="button" className="ml-2 inline-flex items-center gap-1 text-primary hover:underline" onClick={() => setHelp(h => !h)}><HelpCircle className="size-3.5" />Как пользоваться</button>
            </div>
            {help && (
              <ol className="list-decimal space-y-1 rounded-lg border bg-muted/30 p-3 pl-7 text-sm">
                <li>Слева — пункт стандарта, под ним — коды проверок, которые на него ссылаются. Нажмите на код: рядом с текстом пункта откроется описание проверки.</li>
                <li>Значок у кода: без значка — связь подтверждена текстом стандарта, «~» — косвенная, «?» — не сверена.</li>
                <li>Пункт без проверок можно найти фильтром «Без проверок». Если по нему нужна проверка, нажмите «Отметить» и напишите, что проверять.</li>
                <li>Заявка попадает к разработчику, проверку пишет он. Когда проверка готова, заявка получает статус «сделана» и код правила.</li>
                <li>Если описание проверки расходится с текстом пункта, тоже нажмите «Отметить» и напишите, что исправить.</li>
              </ol>
            )}
            {(d.whole.length > 0 || d.stale.length > 0) && (
              <div className="grid gap-1 rounded-lg border p-2 text-xs">
                {d.whole.length > 0 && <div className="flex flex-wrap items-center gap-1"><span className="text-muted-foreground">Проверки ссылаются на стандарт без пункта (показать рядом с пунктом нечего):</span>{d.whole.map(code => <Badge key={code} variant="outline" title={d.codes[code]?.text}>{code}</Badge>)}</div>}
                {d.stale.length > 0 && <div className="text-amber-600">Проверки ссылаются на пункты, которых нет в тексте файла: {d.stale.join(", ")}. Возможно, ссылка устарела или пункт не распознан.</div>}
              </div>
            )}
            <div className="flex flex-wrap items-center gap-2">
              <div className="relative"><Search className="pointer-events-none absolute left-2.5 top-2.5 size-4 text-muted-foreground" />
                <Input className="w-56 pl-8" placeholder="Номер или слово" value={q} onChange={e => setQ(e.target.value)} /></div>
              {([["all", "Все"], ["none", "Без проверок"], ["checked", "С проверками"], ["marked", "Отмеченные"]] as [View, string][]).map(([k, t]) => (
                <Button key={k} size="sm" variant={view === k ? "default" : "outline"} onClick={() => setView(k)}>{t}</Button>
              ))}
            </div>
            <div className="grid gap-2">
              {shown.map(c => (
                <div key={c.n} className={cn("rounded-lg border p-2.5", c.marks.some(m => m.status === "open") && "border-amber-500/60 bg-amber-500/5")}>
                  <div className="flex items-start gap-2">
                    <b className="w-14 shrink-0 text-sm">{c.n}</b>
                    <div className="min-w-0 flex-1 text-sm">
                      <button type="button" className={cn("text-left text-muted-foreground", !full[c.n] && "line-clamp-3")} onClick={() => setFull(f => ({ ...f, [c.n]: !f[c.n] }))} title="Развернуть или свернуть текст">{c.text || "—"}</button>
                      <div className="mt-1 flex flex-wrap items-center gap-1">
                        {c.checks.length > 0 ? chips(c, c.checks) : c.child_checks.length > 0 ? <><span className="text-xs text-muted-foreground">в подпунктах:</span>{chips(c, c.child_checks, true)}</> : <span className="text-xs text-muted-foreground">проверок нет</span>}
                      </div>
                    </div>
                    <div className="flex shrink-0 gap-1">
                      <Button variant="ghost" size="icon-sm" title="Открыть PDF на этой странице" render={<a href={`/norms/${encodeURIComponent(d.id)}#page=${c.page}`} target="_blank" rel="noreferrer" />}><ExternalLink /></Button>
                      <Button variant="outline" size="sm" onClick={() => { setEditing(editing === c.n ? null : c.n); setComment("") }}><Flag />Отметить</Button>
                    </div>
                  </div>
                  {open?.n === c.n && sideBySide(c, open.code)}
                  {c.marks.map(m => (
                    <div key={m.id} className="mt-2 flex flex-wrap items-center gap-2 rounded-md bg-muted/50 px-2 py-1 text-xs">
                      <Badge variant={m.status === "open" ? "default" : "secondary"}>{MARK_LABEL[m.status]}</Badge>
                      <span className="flex-1">{m.comment || "без комментария"} <span className="text-muted-foreground">· {m.author}, {m.created.slice(0, 10)}{m.code && `, правило ${m.code}`}</span></span>
                      {m.status === "open" && <Button variant="ghost" size="xs" onClick={() => void setStatus(m, "done")}>Сделана</Button>}
                      {m.status !== "open" && <Button variant="ghost" size="xs" onClick={() => void setStatus(m, "open")}>Вернуть</Button>}
                      <Button variant="ghost" size="icon-xs" title="Удалить заявку" onClick={() => void remove(m)}><Trash2 /></Button>
                    </div>
                  ))}
                  {editing === c.n && (
                    <div className="mt-2 grid gap-2">
                      <Textarea rows={3} placeholder="Что именно проверять по этому пункту (необязательно)" value={comment} onChange={e => setComment(e.target.value)} />
                      <div className="flex gap-2"><Button size="sm" onClick={() => void mark(c)}>Создать заявку на проверку</Button><Button size="sm" variant="ghost" onClick={() => setEditing(null)}>Отмена</Button></div>
                    </div>
                  )}
                </div>
              ))}
              {shown.length === 0 && <p className="text-sm text-muted-foreground">Ничего не найдено</p>}
            </div>
          </>
        )}
      </SheetContent>
    </Sheet>
  )
}
