import { Fragment, useCallback, useEffect, useMemo, useState } from "react"
import { Info, Pencil, Plus, RotateCcw, Save, Search, Trash2, Undo2 } from "lucide-react"
import { toast } from "sonner"
import { api, errText } from "@/lib/api"
import { useDialogs, type Field } from "@/components/dialogs"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"

interface Item {
  id: number | null
  workshop: string
  type: string
  model: string
  year: number | null
  kind: string
  qty: number
  active: boolean
  params: Record<string, number>
  src: Record<string, string>
}
interface View {
  items: Item[]
  custom: boolean
  kinds: Record<string, string>
  params: Record<string, { label: string; unit: string }>
  kind_params: Record<string, string[]>
  laser_thickness: { kw: number; steel: number; stainless: number; alu: number }[]
}

const SRC_LABEL: Record<string, string> = { model: "по обозначению модели", type: "из названия типа", estimate: "ориентир по таблице", passport: "паспорт", manual: "введено вручную" }
const SRC_DOT: Record<string, string> = { model: "bg-amber-500", type: "bg-amber-500", estimate: "bg-orange-500", passport: "bg-emerald-500", manual: "bg-sky-500" }
const clone = <T,>(o: T): T => JSON.parse(JSON.stringify(o))
const SHORT: Record<string, string> = {
  swing: "Ø обработки", length_max: "Длина", table_l: "Стол: длина", table_w: "Стол: ширина", drill_d: "Ø сверления", spindle_d: "Ø шпинделя",
  gear_d: "Ø колеса", gear_m: "Модуль", laser_kw: "Мощность", bed_l: "Поле: длина", bed_w: "Поле: ширина", t_steel: "Сталь", t_stainless: "Нержавейка",
  t_alu: "Алюминий", tube_l: "Труба: длина", tube_d: "Труба: Ø", roll_w: "Ширина листа", roll_t: "Толщина", brake_l: "Длина гиба", brake_t: "Толщина",
}

export default function EquipmentTab() {
  const dlg = useDialogs()
  const [view, setView] = useState<View | null>(null)
  const [items, setItems] = useState<Item[]>([])
  const [orig, setOrig] = useState("")
  const [q, setQ] = useState("")
  const [kind, setKind] = useState("_")
  const [onlyBlank, setOnlyBlank] = useState(false)
  const [saving, setSaving] = useState(false)

  const apply = useCallback((v: View) => {
    setView(v); setItems(clone(v.items)); setOrig(JSON.stringify(v.items))
  }, [])
  const load = useCallback(async () => { try { apply(await api<View>("/api/admin/equipment")) } catch (e) { toast.error(errText(e)) } }, [apply])
  useEffect(() => { void load() }, [load])

  const dirty = JSON.stringify(items) !== orig

  const counts = useMemo(() => {
    const c: Record<string, number> = {}
    for (const i of items) if (i.active) c[i.kind] = (c[i.kind] || 0) + (i.qty || 1)
    return c
  }, [items])

  const shown = useMemo(() => {
    const s = q.trim().toLowerCase()
    const order = Object.keys(view?.kinds ?? {})
    return items.map((it, idx) => ({ it, idx })).sort((a, b) => order.indexOf(a.it.kind) - order.indexOf(b.it.kind) || a.idx - b.idx).filter(({ it }) =>
      (kind === "_" || it.kind === kind) &&
      (!s || `${it.model} ${it.type} ${it.workshop}`.toLowerCase().includes(s)) &&
      (!onlyBlank || (view?.kind_params[it.kind] || []).some(k => it.params[k] === undefined)))
  }, [items, q, kind, onlyBlank, view])

  if (!view) return <p className="text-sm text-muted-foreground">Загрузка профиля оборудования…</p>
  const K = view.kinds
  const kindOf = (label: string) => Object.entries(K).find(([, v]) => v === label)?.[0] ?? "other"

  const set = (idx: number, patch: Partial<Item>) => setItems(l => l.map((x, i) => (i === idx ? { ...x, ...patch } : x)))

  const paramFields = (k: string, it: Item): Field[] =>
    (view.kind_params[k] || []).map(p => ({
      key: "p_" + p, label: `${view.params[p].label}, ${view.params[p].unit}`, value: it.params[p] !== undefined ? String(it.params[p]) : "",
      placeholder: "не задано",
    }))

  const editDialog = (idx: number, isNew = false, itemArg?: Item) => {
    const it = itemArg ?? items[idx]
    dlg.form(isNew ? "Новое оборудование: уточните параметры" : `Оборудование: ${it.model || it.type}`, [
      { key: "type", label: "Тип (название в списке)", value: it.type },
      { key: "model", label: "Модель", value: it.model },
      { key: "workshop", label: "Участок", value: it.workshop },
      { key: "year", label: "Год выпуска", value: it.year ? String(it.year) : "" },
      { key: "qty", label: "Количество одинаковых станков", value: String(it.qty || 1) },
      { key: "kind", label: "Вид оборудования", type: "select", options: Object.values(K), value: K[it.kind] },
      ...paramFields(it.kind, it),
      { key: "src", label: "Откуда взяты изменённые параметры", type: "select", options: ["паспорт", "введено вручную"], value: "паспорт" },
    ], async v => {
      const k = kindOf(v.kind)
      const params: Record<string, number> = {}
      const src: Record<string, string> = {}
      const fresh = k !== it.kind
      for (const p of view.kind_params[k] || []) {
        const raw = (v["p_" + p] ?? "").trim().replace(",", ".")
        if (!raw) continue
        const n = Number(raw)
        if (Number.isNaN(n)) return `Параметр «${view.params[p].label}»: нужно число`
        params[p] = n
        const old = it.params[p]
        src[p] = !fresh && old === n ? (it.src[p] || "manual") : v.src === "паспорт" ? "passport" : "manual"
      }
      set(idx, { type: v.type.trim(), model: v.model.trim(), workshop: v.workshop.trim(), year: v.year.trim() ? Number(v.year) || null : null,
        qty: Math.max(1, Number(v.qty) || 1), kind: k, params, src })
      return null
    }, { hint: "Параметры, оставленные пустыми, правила не используют (молчат). Числа с пометкой «по обозначению модели» и «ориентир» стоит уточнить по паспорту." })
  }

  const add = () => dlg.form("Добавить оборудование", [
    { key: "type", label: "Тип, например: Станок токарно-винторезный", placeholder: "Станок …" },
    { key: "model", label: "Модель", placeholder: "16К20" },
    { key: "workshop", label: "Участок", placeholder: "401" },
  ], async v => {
    if (!v.type.trim() && !v.model.trim()) return "Заполните тип или модель"
    try {
      const r = await api<{ items: Item[] }>("/api/admin/equipment/preview", { json: { items: [{ type: v.type, model: v.model, workshop: v.workshop }] } })
      const it = r.items[0]
      const idx = items.length
      setItems(l => [...l, it])
      setTimeout(() => editDialog(idx, true, it), 80)
      return null
    } catch (e) { return errText(e) }
  })

  const save = async () => {
    setSaving(true)
    try { apply(await api<View>("/api/admin/equipment", { json: { items } })); toast.success("Профиль оборудования сохранён") } catch (e) { toast.error(errText(e)) }
    setSaving(false)
  }
  const reset = async () => {
    if (!(await dlg.confirm("Вернуть перечень оборудования из ERP?", "Ваши правки профиля будут заменены встроенным списком (104 единицы).", { ok: "Вернуть", danger: true }))) return
    try { apply(await api<View>("/api/admin/equipment/reset", { method: "POST" })); toast.success("Возвращён перечень ERP") } catch (e) { toast.error(errText(e)) }
  }

  const absent = Object.entries(K).filter(([k]) => k !== "other" && !counts[k])
  let lastKind = ""

  return (
    <div className="grid gap-4">
      <Card>
        <CardHeader>
          <CardTitle className="flex flex-wrap items-center gap-2">Профиль оборудования предприятия
            <Badge variant="secondary">{view.custom ? "изменён администратором" : "перечень из ERP"}</Badge>
          </CardTitle>
          <CardDescription>Что производство умеет делать и какие размеры берёт. По этому списку работают проверки группы «Возможности производства» (блок «Технологичность конструкции», по умолчанию выключен): габарит и толщина листа — лазерам, диаметр — токарным станкам, зубчатое колесо — зубообрабатывающим, термообработка и особые операции — печам и установкам.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4">
          <Alert>
            <Info className="size-4" />
            <AlertTitle>Числа выведены автоматически</AlertTitle>
            <AlertDescription>Часть параметров программа определила по обозначению модели станка (например, 16К20 — высота центров 200 мм) и по таблице «мощность лазера — предельная толщина». Это ориентиры: после получения паспортов внесите точные значения — тогда у параметра появится пометка «паспорт». Если параметр не задан, правила по нему молчат и ничего не угадывают.</AlertDescription>
          </Alert>
          <div className="flex flex-wrap gap-1.5">
            {Object.entries(counts).sort((a, b) => b[1] - a[1]).map(([k, n]) => <Badge key={k} variant="outline">{K[k]}: {n}</Badge>)}
          </div>
          {absent.length > 0 && (
            <p className="text-xs text-muted-foreground"><b>В профиле нет:</b> {absent.map(([, v]) => v).join(" · ")}. Правила используют это: например, нет притирочных станков — точность IT4 и Ra 0,1 дадут замечание «нужна кооперация».</p>
          )}
          <div className="flex flex-wrap items-center gap-2">
            <Button onClick={add} variant="outline"><Plus />Добавить станок</Button>
            <Button variant="outline" onClick={() => void reset()}><RotateCcw />Вернуть перечень ERP</Button>
            <span className="flex-1" />
            {dirty && <Button variant="ghost" onClick={() => setItems(JSON.parse(orig))}><Undo2 />Отменить</Button>}
            <Button disabled={!dirty || saving} onClick={() => void save()}><Save />Сохранить профиль</Button>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="gap-3">
          <div className="flex flex-wrap items-center gap-2">
            <div className="relative min-w-64 flex-1">
              <Search className="pointer-events-none absolute left-2.5 top-2.5 size-4 text-muted-foreground" />
              <Input value={q} onChange={e => setQ(e.target.value)} placeholder="Поиск по модели, типу, участку…" className="pl-8" />
            </div>
            <Select value={kind} onValueChange={v => setKind(v ?? "_")}>
              <SelectTrigger className="w-72"><SelectValue>{(v: string) => (v === "_" ? "Все виды оборудования" : K[v])}</SelectValue></SelectTrigger>
              <SelectContent>
                <SelectItem value="_">Все виды оборудования</SelectItem>
                {Object.entries(K).filter(([k]) => counts[k] || items.some(i => i.kind === k)).map(([k, v]) => <SelectItem key={k} value={k}>{v}</SelectItem>)}
              </SelectContent>
            </Select>
            <label className="flex items-center gap-2 text-sm"><Switch checked={onlyBlank} onCheckedChange={setOnlyBlank} />Только с незаданными параметрами</label>
            <span className="text-xs text-muted-foreground">Показано {shown.length} из {items.length}</span>
          </div>
        </CardHeader>
        <CardContent className="px-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-14 pl-6">В работе</TableHead><TableHead className="w-10">№</TableHead><TableHead className="w-16">Уч.</TableHead>
                <TableHead>Модель и тип</TableHead><TableHead>Параметры</TableHead><TableHead className="w-10">Шт.</TableHead>
                <TableHead className="w-20 pr-4" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {shown.map(({ it, idx }) => {
                const head = it.kind !== lastKind
                lastKind = it.kind
                const keys = view.kind_params[it.kind] || []
                return (
                  <Fragment key={idx}>
                    {head && kind === "_" && (
                      <TableRow key={"h" + it.kind + idx} className="bg-muted/50 hover:bg-muted/50">
                        <TableCell colSpan={7} className="py-1.5 pl-6 text-xs font-semibold uppercase tracking-wide text-muted-foreground">{K[it.kind]}</TableCell>
                      </TableRow>
                    )}
                    <TableRow className={it.active ? "" : "opacity-50"}>
                      <TableCell className="pl-6"><Switch checked={it.active} onCheckedChange={v => set(idx, { active: v })} aria-label="В работе" /></TableCell>
                      <TableCell className="text-muted-foreground">{it.id ?? ""}</TableCell>
                      <TableCell>{it.workshop}</TableCell>
                      <TableCell className="whitespace-normal"><b>{it.model}</b><span className="block text-xs text-muted-foreground">{it.type}{it.year ? ` · ${it.year}` : ""}</span></TableCell>
                      <TableCell className="whitespace-normal">
                        <div className="flex flex-wrap gap-1">
                          {keys.map(p => {
                            const v = it.params[p]
                            const s = it.src[p]
                            return v === undefined ? (
                              <Badge key={p} variant="outline" className="border-dashed text-muted-foreground" title={view.params[p].label}>{SHORT[p] || p}: —</Badge>
                            ) : (
                              <Tooltip key={p}>
                                <TooltipTrigger render={<Badge variant="secondary" className="gap-1.5 font-normal" />}>
                                  <span className={`size-1.5 rounded-full ${SRC_DOT[s] || "bg-muted-foreground"}`} />
                                  <span className="text-muted-foreground">{SHORT[p] || p}</span> {v} {view.params[p].unit}
                                </TooltipTrigger>
                                <TooltipContent>{view.params[p].label}: {v} {view.params[p].unit} · {SRC_LABEL[s] || s}</TooltipContent>
                              </Tooltip>
                            )
                          })}
                        </div>
                      </TableCell>
                      <TableCell>{it.qty}</TableCell>
                      <TableCell className="pr-4"><div className="flex justify-end gap-0.5">
                        <Button variant="ghost" size="icon-sm" title="Изменить" onClick={() => editDialog(idx)}><Pencil /></Button>
                        <Button variant="ghost" size="icon-sm" title="Удалить" onClick={() => setItems(l => l.filter((_, i) => i !== idx))}><Trash2 /></Button>
                      </div></TableCell>
                    </TableRow>
                  </Fragment>
                )
              })}
              {shown.length === 0 && <TableRow><TableCell colSpan={7} className="py-10 text-center text-muted-foreground">Ничего не найдено</TableCell></TableRow>}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Ориентир «мощность лазера — предельная толщина резки»</CardTitle>
          <CardDescription>Используется, пока не внесены паспортные значения: практический предел качественной резки, мм. Правится у каждого лазера в карточке станка.</CardDescription>
        </CardHeader>
        <CardContent className="px-0">
          <Table>
            <TableHeader><TableRow><TableHead className="pl-6">Мощность, кВт</TableHead><TableHead>Углеродистая сталь</TableHead><TableHead>Нержавеющая сталь</TableHead><TableHead className="pr-6">Алюминий</TableHead></TableRow></TableHeader>
            <TableBody>{view.laser_thickness.map(r => (
              <TableRow key={r.kw}><TableCell className="pl-6">{r.kw}</TableCell><TableCell>{r.steel}</TableCell><TableCell>{r.stainless}</TableCell><TableCell className="pr-6">{r.alu}</TableCell></TableRow>
            ))}</TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  )
}
