import { useEffect, useState } from "react"
import { BookOpenText, Ban, EyeOff, MessageSquare, ThumbsDown, ThumbsUp, CircleHelp, Undo2, Trash2, ChevronDown, ChevronUp } from "lucide-react"
import { toast } from "sonner"
import { api, errText } from "@/lib/api"
import { useAuth } from "@/lib/auth"
import { useDialogs } from "@/components/dialogs"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu"
import { SEV_LABEL, SevBadge, sevMeta } from "@/components/sev"
import type { DocResult, FbEntry } from "@/lib/types"
import type { NFinding } from "./Viewer"

const FB_LABEL = { ok: "верно", false: "ложное", inexact: "неточно" } as const

const normCache = new Map<string, { id?: string; page?: number; designation?: string } | null>()

function NormLink({ std }: { std: string }) {
  const [r, setR] = useState(normCache.get(std) ?? null)
  useEffect(() => {
    if (normCache.has(std)) { setR(normCache.get(std) ?? null); return }
    api<any>("/api/admin/norms/lookup?std=" + encodeURIComponent(std), { quiet: true })
      .then(x => { normCache.set(std, x); setR(x) }).catch(() => normCache.set(std, null))
  }, [std])
  if (!r?.id) return null
  return (
    <a href={"/norms/" + encodeURIComponent(r.id) + (r.page ? "#page=" + r.page : "")} target="_blank" rel="noreferrer" onClick={e => e.stopPropagation()}
      title={`${r.designation ?? ""}${r.page ? ", стр. " + r.page : ""}`}
      className="inline-flex items-center gap-1 text-xs text-primary hover:underline"><BookOpenText className="size-3" />текст ГОСТ</a>
  )
}

interface Props {
  doc: DocResult
  jobId: string
  findings: NFinding[]
  fb: FbEntry[]
  selected: number | null
  onSelect: (n: number) => void
  onChanged: () => void   // перечитать отчёт
  onFbChanged: () => void // перечитать отметки
}

export default function FindingsTab({ doc, jobId, findings, fb, selected, onSelect, onChanged, onFbChanged }: Props) {
  const { me, isAdmin } = useAuth()
  const dlg = useDialogs()
  const [showHidden, setShowHidden] = useState(false)
  const myName = me?.name ?? ""
  const docFb = fb.filter(e => e.doc === doc.id)

  const send = async (rec: Record<string, unknown>): Promise<string | null> => {
    try {
      await api(`/api/jobs/${jobId}/feedback`, { json: { doc: doc.id, file: doc.file, designation: doc.title.designation, ...rec } })
      onFbChanged()
      return null
    } catch (e) { return errText(e) }
  }
  const verdictOf = (f: NFinding) =>
    docFb.find(x => x.type === "finding" && x.user === myName && x.code === f.code && x.message === f.message)?.verdict ?? null
  const commentsOf = (f: NFinding) => docFb.filter(e => e.type === "comment" && e.code === f.code && e.message === f.message)

  const mark = async (f: NFinding, v: "ok" | "false" | "inexact") => {
    const rec = { type: "finding", verdict: v, code: f.code, message: f.message, page: f.page, bbox: f.bbox }
    if (v === "ok") {
      const e = await send(rec)
      if (e) toast.error(e); else toast.success(`${f.code}: отмечено «верно»`)
      return
    }
    dlg.form(v === "false" ? "Ложное срабатывание" : "Замечание неточное",
      [{ key: "comment", label: v === "false" ? "Почему замечание неверно? (что на чертеже на самом деле)" : "Что неточно?", type: "area", placeholder: "Например: допуск общий, указан в ТТ п. 2" }],
      vals => send({ ...rec, comment: vals.comment }), { hint: `${f.code}: ${f.message}` })
  }

  const comment = (f: NFinding) => dlg.form("Комментарий к замечанию", [
    { key: "comment", label: "Что на самом деле на чертеже / где программа ошиблась", type: "area", placeholder: "Например: размеры 12 и 15 стоят рядом, программа прочитала их как один размер 1215" },
    { key: "expected", label: "Как должно быть (необязательно)", placeholder: "Например: два размера: 12 и 15" },
  ], vals => vals.comment ? send({ type: "comment", code: f.code, message: f.message, page: f.page, bbox: f.bbox, comment: vals.comment, expected: vals.expected }) : Promise.resolve("Напишите комментарий"),
  { hint: `${f.code}: ${f.message}` })

  const exception = async (f: NFinding, scope: "drawing" | "global") => {
    try {
      if (scope === "global") {
        if (!(await dlg.confirm(`Отключить проверку ${f.code} для всех чертежей?`, "Включить её снова можно в «Настройках».", { ok: "Отключить", danger: true }))) return
        await api("/api/admin/rule", { json: { code: f.code, enabled: false } })
      } else {
        await api("/api/exceptions", { json: { scope, code: f.code, message: f.message, designation: doc.title.designation, file: doc.file } })
      }
      onChanged()
    } catch (e) { toast.error(errText(e)) }
  }
  const unexcept = async (id: string) => {
    try { await api("/api/exceptions/" + id, { method: "DELETE" }); onChanged() } catch (e) { toast.error(errText(e)) }
  }
  const delFb = async (id: string) => {
    if (!(await dlg.confirm("Удалить отметку?", undefined, { ok: "Удалить", danger: true }))) return
    await api(`/api/jobs/${jobId}/feedback/${id}`, { method: "DELETE" })
    onFbChanged()
  }

  const cats = [...new Set(findings.map(f => f.category))]
  const hidden = doc.suppressed ?? []

  return (
    <div className="grid gap-4">
      {findings.length === 0 && (
        <p className="rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">
          {doc.findings.length ? "Все замечания скрыты фильтром" : "Замечаний нет"}
        </p>
      )}
      {cats.map(c => (
        <section key={c} className="grid gap-2">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{c}</h3>
          {findings.filter(f => f.category === c).map(f => {
            const m = sevMeta[f.severity]
            const v = verdictOf(f)
            const cm = isAdmin ? commentsOf(f) : []
            return (
              <div key={f.n} id={`finding-${f.n}`} onClick={e => { if (f.bbox && !(e.target as HTMLElement).closest("a,button,[role=button]")) onSelect(f.n) }}
                className={`relative overflow-hidden rounded-lg border bg-card transition ${f.bbox ? "cursor-pointer hover:border-primary/40" : ""} ${selected === f.n ? "ring-2 ring-primary/50" : ""}`}>
                <span className={`absolute inset-y-0 left-0 w-1 ${m.bar}`} />
                <div className="grid gap-2 p-3 pl-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="grid size-5 place-items-center rounded-full bg-foreground text-[11px] font-semibold text-background">{f.n}</span>
                    <SevBadge sev={f.severity}>{SEV_LABEL[f.severity]}</SevBadge>
                    <Badge variant="secondary" className="font-mono">{f.code}</Badge>
                    {f.page !== null && f.page !== undefined && <span className="text-xs text-muted-foreground">лист {f.page + 1}</span>}
                  </div>
                  <p className="text-sm leading-relaxed">{f.message}</p>
                  {f.standard && (
                    <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                      <span>{f.standard}</span>
                      {isAdmin && <NormLink std={f.standard} />}
                    </div>
                  )}
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <ToggleGroup value={v ? [v] : []} onValueChange={val => { const x = val[0] as "ok" | "false" | "inexact" | undefined; if (x) void mark(f, x) }} variant="outline" size="sm" spacing={0}>
                      <Tooltip><TooltipTrigger render={<ToggleGroupItem value="ok" aria-label="Верно" />}><ThumbsUp /><span className="hidden sm:inline">{FB_LABEL.ok}</span></TooltipTrigger><TooltipContent>Замечание правильное</TooltipContent></Tooltip>
                      <Tooltip><TooltipTrigger render={<ToggleGroupItem value="false" aria-label="Ложное" />}><ThumbsDown /><span className="hidden sm:inline">{FB_LABEL.false}</span></TooltipTrigger><TooltipContent>Ложное срабатывание: на чертеже всё в порядке</TooltipContent></Tooltip>
                      <Tooltip><TooltipTrigger render={<ToggleGroupItem value="inexact" aria-label="Неточно" />}><CircleHelp /><span className="hidden sm:inline">{FB_LABEL.inexact}</span></TooltipTrigger><TooltipContent>Замечание по делу, но формулировка или место указаны неточно</TooltipContent></Tooltip>
                    </ToggleGroup>
                    {isAdmin && (
                      <DropdownMenu>
                        <DropdownMenuTrigger render={<Button variant="ghost" size="xs" />}><Ban />Не ошибка</DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem onClick={() => void exception(f, "drawing")}><EyeOff />Скрыть для этого чертежа</DropdownMenuItem>
                          <DropdownMenuItem onClick={() => void exception(f, "global")}><Ban />Отключить правило {f.code} везде</DropdownMenuItem>
                          <DropdownMenuSeparator />
                          <DropdownMenuItem onClick={() => comment(f)}><MessageSquare />Комментарий администратора</DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    )}
                  </div>
                  {cm.map(e => (
                    <div key={e.id} className="rounded-md bg-muted/60 p-2 text-sm">
                      <div className="flex items-center justify-between gap-2 text-xs text-muted-foreground">
                        <span><b className="text-foreground">{e.user}</b> · {e.ts}</span>
                        <Button variant="ghost" size="icon-xs" aria-label="Удалить комментарий" onClick={() => void delFb(e.id)}><Trash2 /></Button>
                      </div>
                      <p>{e.comment}</p>
                      {e.expected && <p className="text-xs text-muted-foreground">Как должно быть: {e.expected}</p>}
                    </div>
                  ))}
                </div>
              </div>
            )
          })}
        </section>
      ))}
      {hidden.length > 0 && (
        <section className="grid gap-2">
          <Button variant="ghost" size="sm" className="w-fit" onClick={() => setShowHidden(s => !s)}>
            {showHidden ? <ChevronUp /> : <ChevronDown />}Скрытые «не ошибка» ({hidden.length})
          </Button>
          {showHidden && hidden.map((f, i) => (
            <div key={i} className="flex items-start gap-3 rounded-lg border border-dashed p-3 opacity-80">
              <div className="min-w-0 flex-1 text-sm">
                <p>{f.message}</p>
                <p className="mt-1 text-xs text-muted-foreground">{f.code} · {f.rule_scope === "global" ? "правило отключено везде" : "отмечено для этого чертежа"}</p>
              </div>
              {f.rule_id && isAdmin && <Button variant="outline" size="xs" onClick={() => void unexcept(f.rule_id!)}><Undo2 />вернуть</Button>}
            </div>
          ))}
        </section>
      )}
    </div>
  )
}
