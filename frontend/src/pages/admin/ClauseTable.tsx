import { useCallback, useEffect, useMemo, useState } from "react"
import { ChevronUp, Search } from "lucide-react"
import { toast } from "sonner"
import { api, errText } from "@/lib/api"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Textarea } from "@/components/ui/textarea"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import { cn } from "@/lib/utils"
import type { Mark } from "./StandardClauses"

interface RuleDoc { what?: string; how?: string; skip?: string }
interface CodeInfo { text: string; sev: string; doc: RuleDoc | null }
interface Clause { n: string; page: number; text: string; checks: string[]; child_checks: string[]; marks: Mark[] }
interface Detail { id: string; designation: string; clauses: Clause[]; whole: string[]; codes: Record<string, CodeInfo>; stale: string[] }
interface Plan { what: string; where: string; how: string; error: string; hardness: string }
interface Idea { n: string; excerpt: string; hint: string; score: number; candidate: boolean; plan: Plan; draft: string }
interface Ideas { items: Idea[] }

type View = "all" | "ideas" | "planned" | "done"
const VIEWS: [View, string][] = [["all", "Все пункты"], ["ideas", "Кандидаты"], ["planned", "Отмечено"], ["done", "Уже проверяется"]]

/** Пункты стандарта как «задачи» в плане: галочка «проверять», описание — как и где это проверяется. */
export function ClauseTable({ fileId, designation, onChanged, onCollapse }: { fileId: string; designation: string; onChanged: () => void; onCollapse: () => void }) {
  const [d, setD] = useState<Detail | null>(null)
  const [ideas, setIdeas] = useState<Record<string, Idea>>({})
  const [err, setErr] = useState("")
  const [q, setQ] = useState("")
  const [view, setView] = useState<View>("all")
  const [full, setFull] = useState<Record<string, boolean>>({})
  const [draft, setDraft] = useState<Record<string, string>>({})

  const load = useCallback(async () => {
    try {
      const [det, sug] = await Promise.all([
        api<Detail>("/api/admin/standards/detail?id=" + encodeURIComponent(fileId)),
        api<Ideas>("/api/admin/standards/suggest?all=1&id=" + encodeURIComponent(fileId)).catch(() => ({ items: [] as Idea[] })),
      ])
      setD(det); setIdeas(Object.fromEntries(sug.items.map(i => [i.n, i]))); setErr("")
    } catch (e) { setErr(errText(e)) }
  }, [fileId])
  useEffect(() => { void load() }, [load])

  const status = (c: Clause) => {
    const open = c.marks.find(m => m.status === "open")
    const done = c.marks.find(m => m.status === "done")
    if (c.checks.length) return "covered" as const
    if (done) return "done" as const
    if (open) return "planned" as const
    return "none" as const
  }

  const shown = useMemo(() => {
    if (!d) return []
    const s = q.trim().toLowerCase()
    return d.clauses.filter(c => {
      const st = status(c)
      if (view === "ideas" && !(st === "none" && ideas[c.n]?.candidate)) return false
      if (view === "planned" && st !== "planned" && st !== "done") return false
      if (view === "done" && st !== "covered") return false
      return !s || (c.n + " " + c.text).toLowerCase().includes(s)
    })
  }, [d, q, view, ideas])

  const count = (st: string) => d ? d.clauses.filter(c => status(c) === st).length : 0

  const toggle = async (c: Clause, on: boolean) => {
    if (!d) return
    try {
      if (on) {
        await api("/api/admin/standards/marks", { json: { file_id: d.id, clause: c.n, text: c.text, comment: ideas[c.n]?.draft ?? "" } })
      } else {
        const m = c.marks.find(x => x.status === "open")
        if (m) await api("/api/admin/standards/marks/" + m.id, { method: "DELETE" })
      }
      await load(); onChanged()
    } catch (e) { toast.error(errText(e)) }
  }

  const saveNote = async (m: Mark) => {
    const v = draft[m.id]
    if (v === undefined || v === m.comment) return
    try { await api("/api/admin/standards/marks/" + m.id, { method: "PATCH", json: { comment: v } }); await load() } catch (e) { toast.error(errText(e)) }
  }

  if (err) return <p className="p-3 text-sm text-destructive">{err}</p>
  if (!d) return <p className="p-3 text-sm text-muted-foreground">Разбираю текст стандарта…</p>

  return (
    <div className="grid gap-2 p-2">
      <div className="sticky top-14 z-10 flex flex-wrap items-center gap-2 border-b bg-background/95 py-2 backdrop-blur">
        <b className="text-sm">{designation}</b>
        <div className="relative"><Search className="pointer-events-none absolute left-2.5 top-2.5 size-4 text-muted-foreground" />
          <Input className="h-9 w-64 pl-8" placeholder="Номер пункта или слово" value={q} onChange={e => setQ(e.target.value)} /></div>
        <ToggleGroup value={[view]} onValueChange={v => v[0] && setView(v[0] as View)} variant="outline" size="sm" spacing={0}>
          {VIEWS.map(([k, t]) => <ToggleGroupItem key={k} value={k}>{t}</ToggleGroupItem>)}
        </ToggleGroup>
        <span className="text-xs text-muted-foreground">
          пунктов: {d.clauses.length} · проверяется: {count("covered")} · отмечено: {count("planned") + count("done")} · кандидатов: {d.clauses.filter(c => status(c) === "none" && ideas[c.n]?.candidate).length}
        </span>
        <Button size="sm" variant="outline" className="ml-auto" onClick={onCollapse}><ChevronUp />Свернуть</Button>
      </div>
      {d.stale.length > 0 && <p className="text-xs text-amber-600">Проверки ссылаются на пункты, которых нет в тексте этого файла: {d.stale.join(", ")}.</p>}
      <div className="rounded-md border bg-background">
        <Table>
          <TableHeader className="bg-muted">
            <TableRow>
              <TableHead className="w-16">Пункт</TableHead>
              <TableHead className="w-[38%]">Требование из стандарта</TableHead>
              <TableHead className="w-24 text-center">Проверять</TableHead>
              <TableHead>Как и где это проверяется</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {shown.length === 0 && <TableRow><TableCell colSpan={4} className="py-6 text-center text-muted-foreground">Ничего не найдено</TableCell></TableRow>}
            {shown.map(c => {
              const st = status(c)
              const open = c.marks.find(m => m.status === "open")
              const done = c.marks.find(m => m.status === "done")
              const idea = ideas[c.n]
              const note = open ? (draft[open.id] ?? open.comment) : ""
              return (
                <TableRow key={c.n} className={cn(st === "covered" && "bg-emerald-500/5", st === "planned" && "bg-amber-500/5")}>
                  <TableCell className="align-top font-mono text-xs">{c.n}<div className="text-[10px] text-muted-foreground">стр. {c.page}</div></TableCell>
                  <TableCell className="whitespace-normal align-top text-sm">
                    <button type="button" className="text-left" onClick={() => setFull(f => ({ ...f, [c.n]: !f[c.n] }))} title="Показать или свернуть весь текст пункта">
                      <span className={full[c.n] ? "" : "line-clamp-3"}>{c.text || "—"}</span>
                    </button>
                  </TableCell>
                  <TableCell className="align-top text-center">
                    <Checkbox
                      checked={st !== "none"}
                      disabled={st === "covered" || st === "done"}
                      onCheckedChange={v => void toggle(c, !!v)}
                      aria-label={`Проверять пункт ${c.n}`}
                    />
                    {st === "covered" && <div className="mt-1 text-[10px] text-emerald-600">есть</div>}
                    {st === "done" && <div className="mt-1 text-[10px] text-emerald-600">сделана</div>}
                    {st === "planned" && <div className="mt-1 text-[10px] text-amber-600">заявка</div>}
                  </TableCell>
                  <TableCell className="whitespace-normal align-top text-sm">
                    {st === "covered" && (
                      <div className="grid gap-1.5">
                        <div className="flex flex-wrap gap-1">{c.checks.map(code => <Badge key={code} variant="secondary" title={d.codes[code]?.text}>{code}</Badge>)}</div>
                        {c.checks.slice(0, 2).map(code => d.codes[code] && (
                          <div key={code} className="text-xs">
                            <b>{code}</b> {d.codes[code].text}
                            {d.codes[code].doc?.how && <div className="text-muted-foreground"><b>Как:</b> {d.codes[code].doc!.how}</div>}
                            {d.codes[code].doc?.skip && <div className="text-muted-foreground"><b>Когда не срабатывает:</b> {d.codes[code].doc!.skip}</div>}
                          </div>
                        ))}
                        {c.checks.length > 2 && <span className="text-xs text-muted-foreground">и ещё проверок: {c.checks.length - 2}</span>}
                      </div>
                    )}
                    {st === "done" && done && <div className="text-xs">{done.code && <Badge variant="secondary" className="mr-1">{done.code}</Badge>}{done.comment}</div>}
                    {st === "planned" && open && (
                      <div className="grid gap-1">
                        <Textarea
                          rows={7}
                          className="min-h-0 text-sm"
                          placeholder="Что проверяем, где на чертеже, как, при каком условии ошибка"
                          value={note}
                          onChange={e => setDraft(x => ({ ...x, [open.id]: e.target.value }))}
                          onBlur={() => void saveNote(open)}
                        />
                        <span className="text-[11px] text-muted-foreground">Черновик составлен программой по тексту пункта, поправьте под себя. Сохраняется при выходе из поля.</span>
                      </div>
                    )}
                    {st === "none" && (idea
                      ? (
                        <div className="grid gap-0.5 text-xs">
                          <div><b>Что:</b> {idea.plan.what}</div>
                          <div><b>Где:</b> {idea.plan.where}</div>
                          <div><b>Как:</b> {idea.plan.how}</div>
                          <div><b>Ошибка, если:</b> {idea.plan.error}</div>
                          <div className="text-muted-foreground"><b>Сложность:</b> {idea.plan.hardness}</div>
                          {!idea.candidate && <div className="italic text-muted-foreground">Пункт мало похож на проверяемое требование; галочку ставьте, если считаете иначе.</div>}
                        </div>
                      )
                      : c.child_checks.length > 0 ? <div className="text-xs text-muted-foreground">В подпунктах проверяется: {c.child_checks.join(", ")}</div> : null)}
                  </TableCell>
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}
