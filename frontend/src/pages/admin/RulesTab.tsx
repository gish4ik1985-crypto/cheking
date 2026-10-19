import { Fragment, useCallback, useEffect, useMemo, useState } from "react"
import { Check, ChevronRight, Info, RotateCcw, Search, Square } from "lucide-react"
import { toast } from "sonner"
import { api, errText } from "@/lib/api"
import { useDialogs } from "@/components/dialogs"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"
import { Textarea } from "@/components/ui/textarea"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import { SEV_SHORT, SevBadge, sevMeta } from "@/components/sev"
import type { Sev } from "@/lib/types"
import { useAdmin, type GroupView, type RuleView, type SectionView, type StdEntry } from "./context"

interface Note { id: string; ts: string; user: string; text: string; status: string; rev?: number; app?: string; dev?: { ts: string; comment: string; rev_after?: number } | null }
interface Review { user: string; ts: string; rev?: number }

const ls = (k: string, d: string) => { try { return localStorage.getItem(k) ?? d } catch { return d } }
const lsSet = (k: string, v: string) => { try { localStorage.setItem(k, v) } catch { /* без хранилища */ } }
const NOTE_TONE: Record<string, string> = { new: "bg-[var(--sev-info-bg)] text-[var(--sev-info)]", accepted: "bg-[var(--sev-warn-bg)] text-[var(--sev-warn)]", rejected: "bg-[var(--sev-error-bg)] text-[var(--sev-error)]", applied: "bg-[var(--sev-ok-bg)] text-[var(--sev-ok)]" }

export default function RulesTab() {
  const { S, rules, setRules, modules, setModules } = useAdmin()
  const dlg = useDialogs()
  const [sel, setSel] = useState(() => ls("admin-group", "overview"))
  const [navMode, setNavMode] = useState<"groups" | "std">(() => (ls("admin-nav", "groups") === "std" ? "std" : "groups"))
  const [selStd, setSelStd] = useState<string | null>(() => ls("admin-std", "") || null)
  const [fstate, setFstate] = useState("")
  const [q, setQ] = useState("")
  const [openDocs, setOpenDocs] = useState<Set<string>>(new Set())
  const [notes, setNotes] = useState<Record<string, Note[]>>({})
  const [statuses, setStatuses] = useState<Record<string, string>>({})
  const [reviews, setReviews] = useState<Record<string, Review>>({})
  const [drafts, setDrafts] = useState<Record<string, string>>({})

  const loadExpert = useCallback(async () => {
    try {
      const j = await api<any>("/api/admin/expert-notes")
      setNotes(j.notes || {}); setStatuses(j.statuses || {}); setReviews(j.reviews || {})
    } catch { /* без мнений */ }
  }, [])
  useEffect(() => { void loadExpert() }, [loadExpert])

  const byCode = useMemo(() => {
    const m: Record<string, { g: GroupView; x: RuleView }> = {}
    for (const g of S.groups) for (const x of g.rules) m[x.code] = { g, x }
    return m
  }, [S.groups])
  const secOf = (key: string) => S.sections.find(s => s.key === key)
  const modOff = (g: GroupView) => { const s = secOf(g.section); return !!(s?.module && !modules[s.key]) }
  const effSev = (x: RuleView): Sev => (rules[x.code].severity as Sev) || x.typical
  const isChanged = (x: RuleView) => rules[x.code].enabled !== x.default || !!rules[x.code].severity
  const groupOn = (g: GroupView) => g.rules.filter(x => rules[x.code].enabled).length
  const searching = !!q.trim()

  const matches = (g: GroupView, x: RuleView) => {
    const s = q.trim().toLowerCase()
    if (s && !(g.title + " " + g.standards + " " + x.code + " " + x.text).toLowerCase().includes(s)) return false
    const st = rules[x.code]
    if (fstate === "notes" && !(notes[x.code] || []).length) return false
    if (fstate === "todo" && reviews[x.code]) return false
    if (fstate === "done" && !reviews[x.code]) return false
    return !((fstate === "on" && !st.enabled) || (fstate === "off" && st.enabled) || (fstate === "changed" && !isChanged(x)))
  }
  const stdsOf = (code: string) => S.standards.filter(e => e.direct.some(d => d.code === code)).map(e => ({ key: e.key, label: e.label, clauses: e.direct.find(d => d.code === code)!.clauses }))

  const choose = (key: string) => { setSel(key); lsSet("admin-group", key); setNavMode("groups"); lsSet("admin-nav", "groups"); setQ(""); window.scrollTo({ top: 0 }) }
  const chooseStd = (key: string | null) => { setSelStd(key); lsSet("admin-std", key || ""); setNavMode("std"); lsSet("admin-nav", "std"); setQ(""); window.scrollTo({ top: 0 }) }
  const setMode = (m: "groups" | "std") => { setNavMode(m); lsSet("admin-nav", m); setQ("") }
  const setRule = (code: string, patch: Partial<{ enabled: boolean; severity: string }>) => setRules(r => ({ ...r, [code]: { ...r[code], ...patch } }))

  const reviewToggle = async (code: string) => {
    try {
      const j = await api<any>("/api/admin/rule-review", { json: { code, reviewed: !reviews[code] } })
      setReviews(r => { const n = { ...r }; if (j.review) n[code] = j.review; else delete n[code]; return n })
    } catch (e) { toast.error(errText(e)) }
  }
  const sendNote = async (code: string) => {
    const text = (drafts[code] || "").trim()
    if (!text) { toast.error("Напишите, что и как должно проверяться"); return }
    try {
      const j = await api<Note>("/api/admin/expert-notes", { json: { code, text } })
      setNotes(n => ({ ...n, [code]: [j, ...(n[code] || [])] }))
      setReviews(r => { const n = { ...r }; delete n[code]; return n })
      setDrafts(d => ({ ...d, [code]: "" }))
      toast.success("Мнение отправлено")
    } catch (e) { toast.error(errText(e)) }
  }
  const delNote = async (id: string) => {
    if (!(await dlg.confirm("Удалить это мнение?", undefined, { ok: "Удалить", danger: true }))) return
    try { await api("/api/admin/expert-notes/" + id, { method: "DELETE" }); await loadExpert() } catch (e) { toast.error(errText(e)) }
  }
  const toggleDoc = (code: string) => setOpenDocs(s => { const n = new Set(s); n.has(code) ? n.delete(code) : n.add(code); return n })

  const ReviewBtn = ({ x }: { x: RuleView }) => {
    const r = reviews[x.code]
    if (!r) return <Button variant="ghost" size="xs" className="text-muted-foreground" onClick={() => void reviewToggle(x.code)} title="Отметить, что правило утверждено: администратор согласен с ним и к нему не возвращается. Отметку увидят все администраторы"><Square />Утверждено</Button>
    const old = (x.rev || 1) > (r.rev || 1)
    return (
      <Button variant="secondary" size="xs" className={old ? "text-[var(--sev-warn)]" : "text-[var(--sev-ok)]"} onClick={() => void reviewToggle(x.code)}
        title={`Отметил ${r.user}, ${r.ts}${old ? `. После отметки правило изменено (ревизия ${x.rev || 1}) — стоит просмотреть заново` : ""}. Нажмите, чтобы снять отметку`}>
        <Check />Утверждено{old ? " (правило изменено)" : ""}
      </Button>
    )
  }

  const DocBlock = ({ x }: { x: RuleView }) => {
    const d = x.doc
    const row = (t: string, v?: string) => v ? <div className="grid gap-0.5 sm:grid-cols-[140px_1fr]"><b className="text-xs text-muted-foreground">{t}</b><div className="text-sm">{v}</div></div> : null
    const list = notes[x.code] || []
    return (
      <div className="col-span-full mt-2 grid gap-3 rounded-lg bg-muted/50 p-3">
        {d ? (
          <>
            {row("Что проверяется", (d.what || "").replace(/^Что\s+/, "").replace(/^./, ch => ch.toUpperCase()))}
            {row("Как определяется", d.how)}{row("Пример замечания", d.example)}{row("Когда не срабатывает", d.skip)}{row("Настройки", d.params)}
            <p className="text-xs text-muted-foreground">Код {x.code} · ревизия правила {x.rev || 1}{x.default ? "" : " · по умолчанию выключена"}</p>
          </>
        ) : <p className="text-sm text-muted-foreground">Описание для этой проверки пока не написано.</p>}
        <div className="grid gap-2 border-t pt-3">
          <b className="text-sm">Мнение эксперта</b>
          <p className="text-xs text-muted-foreground">Что и как должна проверять эта проверка, как на неё реагировать: важность, формулировка замечания, когда не срабатывать. Разработчик перепроверит мнение по стандарту и ответит здесь; при необходимости правило будет изменено.</p>
          <Textarea rows={3} maxLength={4000} value={drafts[x.code] || ""} onChange={e => setDrafts(d => ({ ...d, [x.code]: e.target.value }))}
            placeholder="Например: проверять не только поле допуска, но и ...; при ... выдавать предупреждение, а не ошибку" />
          <div className="flex flex-wrap items-center gap-2">
            <Button size="sm" onClick={() => void sendNote(x.code)}>Отправить мнение</Button>
            {ReviewBtn({ x })}
            <span className="text-xs text-muted-foreground">Новое мнение снимает отметку «Утверждено».</span>
          </div>
          {list.map(n => (
            <div key={n.id} className="rounded-md border bg-card p-2.5 text-sm">
              <div className="mb-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                <Badge variant="outline" className={NOTE_TONE[n.status] || NOTE_TONE.new}>{statuses[n.status] || n.status}</Badge>
                <span>{n.ts} · {n.user} · ревизия правила {n.rev || 1}{n.app ? ` · версия ${n.app}` : ""}</span>
                {n.status === "new" && <Button className="ml-auto" variant="ghost" size="xs" onClick={() => void delNote(n.id)}>удалить</Button>}
              </div>
              <p className="whitespace-pre-wrap">{n.text}</p>
              {n.dev && (
                <div className="mt-2 rounded-md bg-muted p-2">
                  <p className="text-xs"><b>Ответ разработчика</b> <span className="text-muted-foreground">{n.dev.ts}{n.dev.rev_after ? ` · ревизия правила ${n.dev.rev_after}` : ""}</span></p>
                  <p className="whitespace-pre-wrap">{n.dev.comment}</p>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    )
  }

  const RuleRow = ({ g, x, onlyStd }: { g: GroupView; x: RuleView; onlyStd?: string }) => {
    const st = rules[x.code]
    const chips = stdsOf(x.code)
    const noteN = (notes[x.code] || []).length
    return (
      <div id={`rule-${x.code}`} className={`grid grid-cols-[auto_auto_1fr_auto_auto] items-start gap-x-3 gap-y-1 border-t px-4 py-2.5 first:border-t-0 ${st.enabled ? "" : "opacity-60"}`}>
        <Switch checked={st.enabled} disabled={g.locked} onCheckedChange={v => setRule(x.code, { enabled: v })} aria-label={`Правило ${x.code}`} className="mt-0.5" />
        <Badge variant="secondary" className="mt-0.5 font-mono">{x.code}</Badge>
        <div className="min-w-0 text-sm">
          <span>{x.text}</span>
          {isChanged(x) && <span title="Отличается от настройки по умолчанию" className="ml-1.5 inline-block size-1.5 rounded-full bg-primary align-middle" />}
          {!x.default && <span className="text-xs text-muted-foreground"> · по умолчанию выключена</span>}
          {chips.length > 0 && (
            <div className="mt-1 flex flex-wrap gap-1">
              {chips.map(e => {
                const cl = e.clauses.length ? " " + e.clauses.join(", ") : ""
                return onlyStd === e.key
                  ? (cl ? <Badge key={e.key} variant="outline" className="text-xs">{cl.trim()}</Badge> : null)
                  : <button key={e.key} onClick={() => chooseStd(e.key)} title="Показать все проверки по этому стандарту"><Badge variant="outline" className="cursor-pointer text-xs hover:bg-accent">{e.label + cl}</Badge></button>
              })}
            </div>
          )}
          <div className="mt-1">{ReviewBtn({ x })}</div>
        </div>
        <Button variant={openDocs.has(x.code) ? "secondary" : "ghost"} size="icon-sm" onClick={() => toggleDoc(x.code)} aria-label={`Как работает проверка ${x.code}`}
          title={`Что проверяется и как${noteN ? " · есть мнения эксперта: " + noteN : ""}`} className="relative">
          <Info />{noteN > 0 && <span className="absolute -right-1 -top-1 grid size-4 place-items-center rounded-full bg-primary text-[10px] text-primary-foreground">{noteN}</span>}
        </Button>
        <Select value={st.severity || "_"} disabled={g.locked} onValueChange={v => setRule(x.code, { severity: v === "_" ? "" : (v ?? "") })}>
          <SelectTrigger size="sm" className="w-44">
            <SelectValue>{(v: string) => { const s = (v === "_" ? x.typical : v) as Sev; return <span className="flex items-center gap-2"><span className={`size-2 rounded-full ${sevMeta[s].bar}`} />{SEV_SHORT[s]}{v === "_" ? " (обычно)" : ""}</span> }}</SelectValue>
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="_">{SEV_SHORT[x.typical]} (обычно)</SelectItem>
            {(["error", "warning", "info"] as Sev[]).filter(k => k !== x.typical).map(k => <SelectItem key={k} value={k}>{SEV_SHORT[k]}</SelectItem>)}
          </SelectContent>
        </Select>
        {openDocs.has(x.code) && DocBlock({ x })}
      </div>
    )
  }

  const stdChips = (g: GroupView) => (g.standards || "").split(/,\s*(?=ГОСТ|ОСТ|СТП|ISO)/).filter(Boolean).map(s => <Badge key={s} variant="outline" className="text-xs">{s}</Badge>)
  const sevCounts = (g: GroupView) => {
    const c: Record<Sev, number> = { error: 0, warning: 0, info: 0 }
    for (const x of g.rules) if (rules[x.code].enabled) c[effSev(x)]++
    return (Object.entries(c) as [Sev, number][]).filter(([, n]) => n).map(([k, n]) => <SevBadge key={k} sev={k}>{SEV_SHORT[k]}: {n}</SevBadge>)
  }
  const ModBlock = ({ s }: { s: SectionView }) => !s.module ? null : (
    <div className={`mb-3 flex items-center justify-between gap-4 rounded-lg border p-3 ${modules[s.key] ? "border-[var(--sev-ok)]/40 bg-[var(--sev-ok-bg)]" : "bg-muted/40"}`}>
      <div>
        <b className="text-sm">{modules[s.key] ? "Блок включён" : "Блок выключен"}</b>
        <p className="text-xs text-muted-foreground">{s.module.descr} Проверки этого блока не смешиваются с проверками ЕСКД: пока блок выключен, их замечаний нет ни в одном отчёте.</p>
      </div>
      <Switch checked={!!modules[s.key]} onCheckedChange={v => setModules(m => ({ ...m, [s.key]: v }))} aria-label="Включить блок" />
    </div>
  )

  const GroupBlock = ({ g, list, compact }: { g: GroupView; list: RuleView[]; compact: boolean }) => {
    const on = groupOn(g)
    const done = (g.clauses || []).filter(c => c[2]).length
    return (
      <Card className={`overflow-hidden ${modOff(g) ? "opacity-60" : ""}`}>
        <div className="flex flex-wrap items-start justify-between gap-3 p-4">
          <div className="grid min-w-0 gap-1.5">
            <div className="text-base font-semibold">{compact ? <button className="hover:underline" onClick={() => choose(g.key)}>{g.title}</button> : g.title}</div>
            <div className="flex flex-wrap gap-1">{stdChips(g)}</div>
            {!compact && <p className="text-sm text-muted-foreground">{g.description}</p>}
          </div>
          <div className="flex items-center gap-3">
            <span className="text-xs text-muted-foreground">включено {on} из {g.rules.length}</span>
            <Switch checked={on === g.rules.length && g.rules.length > 0} disabled={g.locked} title="Включить или выключить все проверки группы"
              onCheckedChange={v => setRules(r => { const n = { ...r }; for (const x of g.rules) n[x.code] = { ...n[x.code], enabled: v }; return n })} />
          </div>
        </div>
        {!compact && <div className="flex flex-wrap gap-1 px-4 pb-3">{sevCounts(g)}</div>}
        {!compact && g.clauses && g.clauses.length > 0 && (
          <details open className="border-t">
            <summary className="cursor-pointer px-4 py-2 text-sm font-medium">Пункты стандарта — проверяется по чертежу {done} из {g.clauses.length}</summary>
            <div className="px-4 pb-3 text-sm">
              {g.clauses.map(([p, t, code], i) => (
                <div key={i} className={`grid grid-cols-[90px_1fr_130px] gap-2 border-t py-1.5 ${code ? "" : "text-muted-foreground"}`}>
                  <span className="font-mono text-xs">п. {p}</span><span>{t}</span>
                  <span className="flex flex-wrap gap-1">{code ? code.split(",").map(c => c.trim()).map(c => (
                    <a key={c} href={`#rule-${c}`} className="font-mono text-xs text-primary hover:underline" onClick={e => {
                      e.preventDefault()
                      const el = document.getElementById("rule-" + c)
                      if (el) { el.scrollIntoView({ behavior: "smooth", block: "center" }); el.classList.add("bg-primary/10"); setTimeout(() => el.classList.remove("bg-primary/10"), 1400) }
                    }}>{c}</a>)) : <span className="text-xs">не проверяется</span>}</span>
                </div>
              ))}
            </div>
          </details>
        )}
        <div className="border-t">
          {list.length ? list.map(x => <Fragment key={x.code}>{RuleRow({ g, x })}</Fragment>) : <p className="p-4 text-sm text-muted-foreground">Нет проверок под фильтр</p>}
        </div>
      </Card>
    )
  }

  const Overview = () => (
    <div className="grid gap-5">
      {S.sections.map(s => {
        const gs = S.groups.filter(g => g.section === s.key)
        return (
          <section key={s.key}>
            <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold">{s.title}{s.module && <Badge variant="secondary">отдельный блок</Badge>}</h3>
            {ModBlock({ s })}
            <div className={`grid gap-3 sm:grid-cols-2 xl:grid-cols-3 ${s.module && !modules[s.key] ? "opacity-60" : ""}`}>
              {gs.map(g => {
                const on = groupOn(g), n = g.rules.length, ch = g.rules.filter(isChanged).length
                return (
                  <button key={g.key} onClick={() => choose(g.key)} className="grid gap-1.5 rounded-xl border bg-card p-3 text-left transition hover:border-primary/50 hover:bg-accent/40">
                    <b className="text-sm">{g.title}</b>
                    <span className="text-xs text-muted-foreground">{g.standards}</span>
                    <span className="h-1.5 overflow-hidden rounded bg-muted"><i className="block h-full bg-primary" style={{ width: `${n ? Math.round((100 * on) / n) : 0}%` }} /></span>
                    <span className="text-xs">{n ? `${on} из ${n} включено` : "нет проверок"}{ch ? <span className="text-primary"> · изменено {ch}</span> : null}</span>
                  </button>
                )
              })}
            </div>
          </section>
        )
      })}
    </div>
  )

  const stdMatches = (e: StdEntry) => {
    const s = q.trim().toLowerCase()
    if (!s) return true
    if (e.label.toLowerCase().includes(s)) return true
    return e.direct.some(d => byCode[d.code] && matches(byCode[d.code].g, byCode[d.code].x))
  }
  const groupTitle = (k: string) => S.groups.find(g => g.key === k)?.title || k

  const StdOverview = () => {
    const list = S.standards.filter(stdMatches)
    if (!list.length) return <p className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">Ничего не найдено</p>
    return (
      <Card className="overflow-hidden">
        {list.map(e => (
          <button key={e.key} onClick={() => chooseStd(e.key)} className="grid w-full grid-cols-[1fr_auto] items-center gap-3 border-t px-4 py-2.5 text-left transition first:border-t-0 hover:bg-accent/50">
            <span><b className="text-sm">{e.label}</b><span className="block text-xs text-muted-foreground">{e.groups.map(groupTitle).join(" · ")}</span></span>
            <span className="text-sm">{e.direct.length}{e.related.length > 0 && <span className="text-xs text-muted-foreground"> + {e.related.length} в группе</span>}</span>
          </button>
        ))}
      </Card>
    )
  }
  const StdCard = ({ e }: { e: StdEntry }) => {
    const rowFor = (c: string) => byCode[c] ? <Fragment key={c}>{RuleRow({ g: byCode[c].g, x: byCode[c].x, onlyStd: e.key })}</Fragment> : null
    const direct = e.direct.filter(d => byCode[d.code] && matches(byCode[d.code].g, byCode[d.code].x))
    const rel = e.related.filter(c => byCode[c] && matches(byCode[c].g, byCode[c].x))
    const onN = e.direct.filter(d => rules[d.code]?.enabled).length
    return (
      <Card className="overflow-hidden">
        <div className="grid gap-1.5 p-4">
          <div className="text-base font-semibold">{e.label}</div>
          <div className="flex flex-wrap gap-1">{e.groups.map(k => <button key={k} onClick={() => choose(k)}><Badge variant="outline" className="cursor-pointer text-xs hover:bg-accent">{groupTitle(k)}</Badge></button>)}</div>
          <p className="text-sm text-muted-foreground">Проверок, которые ссылаются на стандарт: {e.direct.length} (включено {onN}){e.related.length ? `; ещё ${e.related.length} из тех же групп` : ""}</p>
        </div>
        <div className="border-t">{direct.length ? direct.map(d => rowFor(d.code)) : <p className="p-4 text-sm text-muted-foreground">Нет проверок под фильтр</p>}</div>
        {rel.length > 0 && (
          <details className="border-t"><summary className="cursor-pointer px-4 py-2 text-sm font-medium">Другие проверки тех же групп ({rel.length}) — стандарт в замечании не называется</summary>
            <div className="border-t">{rel.map(rowFor)}</div></details>
        )}
      </Card>
    )
  }

  const filt = searching || !!fstate
  const cnt = (g: GroupView) => g.rules.filter(x => matches(g, x)).length
  const all = S.groups.reduce((a, g) => a + g.rules.length, 0)
  const total = Object.keys(rules).length, onAll = Object.values(rules).filter(r => r.enabled).length
  const offN = S.groups.filter(modOff).reduce((a, g) => a + groupOn(g), 0)

  const visible = () => {
    const out: { g: GroupView; list: RuleView[] }[] = []
    for (const g of S.groups) {
      if (!(sel === "overview" || sel === g.key || searching)) continue
      out.push({ g, list: g.rules.filter(x => matches(g, x)) })
    }
    return out
  }

  const Main = () => {
    if (navMode === "std") {
      const e = S.standards.find(x => x.key === selStd)
      return e && !searching ? StdCard({ e }) : StdOverview()
    }
    if (sel === "overview" && !searching && !fstate) return Overview()
    const single = !searching && sel !== "overview"
    const gs = visible().filter(v => v.list.length || (single && v.g.key === sel))
    const head = single ? (() => { const s = secOf(S.groups.find(x => x.key === sel)?.section || ""); return s ? ModBlock({ s }) : null })() : null
    return gs.length ? <div className="grid gap-3">{head}{gs.map(({ g, list }) => <Fragment key={g.key}>{GroupBlock({ g, list, compact: !single })}</Fragment>)}</div>
      : <p className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">Ничего не найдено</p>
  }

  return (
    <div className="grid gap-4 lg:grid-cols-[280px_minmax(0,1fr)]">
      <aside className="grid h-fit content-start gap-2 lg:sticky lg:top-20">
        <ToggleGroup value={[navMode]} onValueChange={v => v[0] && setMode(v[0] as "groups" | "std")} variant="outline" size="sm" spacing={0} className="w-full">
          <ToggleGroupItem value="groups" className="flex-1">По разделам</ToggleGroupItem>
          <ToggleGroupItem value="std" className="flex-1">По стандартам</ToggleGroupItem>
        </ToggleGroup>
        <div className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-2.5 size-4 text-muted-foreground" />
          <Input value={q} onChange={e => setQ(e.target.value)} placeholder="Поиск: ГОСТ, код, текст…" className="pl-8" autoComplete="off" />
        </div>
        <nav className="max-h-[calc(100svh-14rem)] overflow-auto rounded-xl border bg-card p-1.5">
          {navMode === "std" ? (
            <>
              <button onClick={() => chooseStd(null)} className={`flex w-full items-center justify-between rounded-lg px-2.5 py-1.5 text-left text-sm hover:bg-accent ${!selStd ? "bg-accent font-medium" : ""}`}><span>Все стандарты</span><span className="text-xs text-muted-foreground">{S.standards.length}</span></button>
              {S.standards.filter(stdMatches).map(e => (
                <button key={e.key} onClick={() => chooseStd(e.key)} className={`flex w-full items-center justify-between gap-2 rounded-lg px-2.5 py-1.5 text-left text-sm hover:bg-accent ${selStd === e.key && !searching ? "bg-accent font-medium" : ""}`}>
                  <span>{e.label}</span><span className="text-xs text-muted-foreground">{e.direct.length}</span>
                </button>
              ))}
            </>
          ) : (
            <>
              <button onClick={() => choose("overview")} className={`flex w-full items-center justify-between rounded-lg px-2.5 py-1.5 text-left text-sm hover:bg-accent ${sel === "overview" && !searching ? "bg-accent font-medium" : ""}`}><span>Обзор</span><span className="text-xs text-muted-foreground">{all}</span></button>
              {S.sections.map(s => (
                <div key={s.key}>
                  <div className="mt-2 flex items-center justify-between px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                    <span>{s.title}</span>{s.module && <span className={modules[s.key] ? "text-[var(--sev-ok)]" : ""}>{modules[s.key] ? "включён" : "выключен"}</span>}
                  </div>
                  {S.groups.filter(g => g.section === s.key).map(g => {
                    const on = groupOn(g), n = g.rules.length, m = filt ? cnt(g) : null
                    return (
                      <button key={g.key} title={g.standards} onClick={() => choose(g.key)}
                        className={`flex w-full items-center justify-between gap-2 rounded-lg px-2.5 py-1.5 text-left text-sm hover:bg-accent ${sel === g.key && !searching ? "bg-accent font-medium" : ""} ${filt && !m ? "opacity-40" : ""}`}>
                        <span>{g.title}</span>
                        <Badge variant={on === n && n ? "secondary" : "outline"} className={on === 0 ? "text-muted-foreground" : ""}>{filt ? m : `${on}/${n}`}</Badge>
                      </button>
                    )
                  })}
                </div>
              ))}
            </>
          )}
        </nav>
      </aside>
      <div className="grid min-w-0 content-start gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <ToggleGroup value={[fstate || "all"]} onValueChange={v => setFstate(v[0] && v[0] !== "all" ? v[0] : "")} variant="outline" size="sm" spacing={0}>
            <ToggleGroupItem value="all">Все</ToggleGroupItem><ToggleGroupItem value="on">Включённые</ToggleGroupItem><ToggleGroupItem value="off">Выключенные</ToggleGroupItem>
            <ToggleGroupItem value="changed">Изменённые</ToggleGroupItem><ToggleGroupItem value="notes" title="Проверки, по которым есть мнение эксперта">С мнением</ToggleGroupItem>
            <ToggleGroupItem value="todo" title="Проверки, которые ещё не отмечены как утверждённые">Не утверждены</ToggleGroupItem>
            <ToggleGroupItem value="done" title="Проверки, отмеченные как утверждённые">Утверждены</ToggleGroupItem>
          </ToggleGroup>
          <span className="flex-1" />
          <span className="text-xs text-muted-foreground">Включено {onAll - offN} из {total} проверок{offN ? ` · ещё ${offN} ждут включения блока` : ""}</span>
          <Button variant="outline" size="sm" title="Показать или скрыть описание «что и как проверяется» у всех проверок на экране" onClick={() => {
            const codes = [...document.querySelectorAll<HTMLElement>("[id^=rule-]")].map(e => e.id.replace("rule-", ""))
            const allOpen = codes.length > 0 && codes.every(c => openDocs.has(c))
            setOpenDocs(s => { const n = new Set(s); for (const c of codes) allOpen ? n.delete(c) : n.add(c); return n })
          }}><ChevronRight />Описания</Button>
          <Button variant="outline" size="sm" title="Вернуть включение и важность всех проверок, как задано в программе" onClick={async () => {
            if (!(await dlg.confirm("Вернуть все проверки к настройкам по умолчанию?", "Изменения применятся после «Сохранить».", { ok: "Вернуть" }))) return
            setRules(r => { const n = { ...r }; for (const g of S.groups) for (const x of g.rules) n[x.code] = { enabled: x.default, severity: "" }; return n })
            setModules(m => { const n = { ...m }; for (const s of S.sections) if (s.module) n[s.key] = s.module.default; return n })
          }}><RotateCcw />По умолчанию</Button>
        </div>
        {Main()}
      </div>
    </div>
  )
}
