import { useCallback, useEffect, useState } from "react"
import { BookOpen, ChevronDown, ChevronRight, Search } from "lucide-react"
import { api, errText } from "@/lib/api"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Switch } from "@/components/ui/switch"
import { cn } from "@/lib/utils"
import { useAdmin } from "./context"

interface Info { available: boolean; version: string; source: string; counts: Record<string, number>; rules: { code: string; text: string; sev: string }[] }
interface Node { code: string; name: string; level: string; has_children: boolean }
interface Hit { code: string; name: string; path: string; index?: string }

function Tree({ prefix, depth }: { prefix: string; depth: number }) {
  const [items, setItems] = useState<Node[] | null>(null)
  const [open, setOpen] = useState<Record<string, boolean>>({})
  useEffect(() => { void api<Node[]>("/api/admin/classifier/children?prefix=" + prefix).then(setItems).catch(() => setItems([])) }, [prefix])
  if (!items) return <p className="py-1 text-xs text-muted-foreground" style={{ paddingLeft: depth * 16 }}>Загрузка…</p>
  return (
    <div>
      {items.map(n => (
        <div key={n.code}>
          <div className="flex items-start gap-1 py-0.5 text-sm" style={{ paddingLeft: depth * 16 }}>
            {n.has_children
              ? <button type="button" className="mt-0.5 shrink-0 text-muted-foreground" onClick={() => setOpen(o => ({ ...o, [n.code]: !o[n.code] }))}>{open[n.code] ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}</button>
              : <span className="w-4 shrink-0" />}
            <code className="shrink-0 rounded bg-muted px-1.5 text-xs leading-5">{n.code}</code>
            <span className="min-w-0">{n.name}</span>
          </div>
          {open[n.code] && <Tree prefix={n.code} depth={depth + 1} />}
        </div>
      ))}
    </div>
  )
}

export function ClassifierTab() {
  const { S, modules, setModules } = useAdmin()
  const sec = S.sections.find(s => s.key === "cls")
  const [info, setInfo] = useState<Info | null>(null)
  const [err, setErr] = useState("")
  const [q, setQ] = useState("")
  const [hits, setHits] = useState<Hit[] | null>(null)
  const [doc, setDoc] = useState<"pz" | "vv" | null>(null)
  useEffect(() => { void api<Info>("/api/admin/classifier/info").then(setInfo).catch(e => setErr(errText(e))) }, [])

  const find = useCallback(async () => {
    if (q.trim().length < 2) { setHits(null); return }
    try { setHits(await api<Hit[]>("/api/admin/classifier/search?q=" + encodeURIComponent(q.trim()))) } catch (e) { setErr(errText(e)) }
  }, [q])
  const on = !!modules["cls"]

  return (
    <div className="grid gap-4">
      <Card>
        <CardHeader>
          <CardTitle>Классификатор ЕСКД</CardTitle>
          <CardDescription>
            Код классификации из обозначения («741211» в «ЮМЛТ.741211.022») сверяется с классификатором: есть ли он в классификаторе, что означает и согласуется ли с чертежом.
            Это пробный блок: пока он выключен, его замечаний нет ни в одном отчёте. Включайте и выключайте его целиком переключателем ниже, затем нажмите «Сохранить» вверху страницы.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3">
          <div className={cn("flex items-center justify-between gap-4 rounded-lg border p-3", on ? "border-[var(--sev-ok)]/40 bg-[var(--sev-ok-bg)]" : "bg-muted/40")}>
            <div>
              <b className="text-sm">{on ? "Блок включён" : "Блок выключен"}</b>
              <p className="text-xs text-muted-foreground">{sec?.module?.descr}</p>
            </div>
            <Switch checked={on} onCheckedChange={v => setModules(m => ({ ...m, cls: v }))} aria-label="Включить блок «Классификатор ЕСКД»" />
          </div>
          {err && <p className="text-sm text-destructive">{err}</p>}
          {info && !info.available && <p className="text-sm text-destructive">Данные классификатора не найдены (папка classifier). Соберите их: python tools/build_classifier.py.</p>}
          {info && info.available && (
            <p className="text-xs text-muted-foreground">
              {info.source}, версия {info.version}. Записей: {info.counts.total} (классов {info.counts.class}, подклассов {info.counts.subclass}, групп {info.counts.group}, подгрупп {info.counts.subgroup}, видов {info.counts.kind}).
            </p>
          )}
          {info && (
            <div className="grid gap-1 rounded-lg border p-3 text-sm">
              <b>Проверки блока</b>
              {info.rules.map(r => (
                <div key={r.code} className="flex items-center gap-2"><Badge variant="secondary">{r.code}</Badge><span>{r.text}</span><span className="text-xs text-muted-foreground">({r.sev === "warning" ? "предупреждение" : r.sev === "error" ? "ошибка" : "информация"})</span></div>
              ))}
              <p className="text-xs text-muted-foreground">Включить или отключить отдельную проверку можно и на вкладке «Проверки по стандартам», раздел «Классификатор ЕСКД».</p>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Справочник</CardTitle>
          <CardDescription>Поиск по коду (начало кода) или по слову в названии; ниже можно раскрывать дерево от классов до видов.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3">
          <div className="flex flex-wrap items-center gap-2">
            <div className="relative"><Search className="pointer-events-none absolute left-2.5 top-2.5 size-4 text-muted-foreground" />
              <Input className="w-80 pl-8" placeholder="Например 741211 или «пластина»" value={q} onChange={e => setQ(e.target.value)} onKeyDown={e => { if (e.key === "Enter") void find() }} /></div>
            <Button variant="outline" onClick={() => void find()}>Найти</Button>
            {hits && <Button variant="ghost" onClick={() => { setHits(null); setQ("") }}>Сбросить</Button>}
          </div>
          {hits && (hits.length === 0 ? <p className="text-sm text-muted-foreground">Ничего не найдено</p> : (
            <div className="grid gap-1">
              {hits.map(h => (
                <div key={h.code} className="rounded-md border p-2 text-sm">
                  <code className="rounded bg-muted px-1.5 text-xs">{h.code}</code> <b>{h.name}</b>
                  {h.index && <span className="text-xs text-muted-foreground"> (указатель: {h.index})</span>}
                  <div className="text-xs text-muted-foreground">{h.path}</div>
                </div>
              ))}
            </div>
          ))}
          {!hits && <div className="max-h-[60vh] overflow-y-auto rounded-lg border p-2"><Tree prefix="" depth={0} /></div>}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Пояснительная записка и введение</CardTitle>
          <CardDescription>Тексты из справки классификатора: «Иллюстрированный определитель деталей классов 71–76. Пояснительная записка» (с рисунками) и «Введение».</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3">
          <div className="flex gap-2">
            <Button variant={doc === "pz" ? "default" : "outline"} onClick={() => setDoc(doc === "pz" ? null : "pz")}><BookOpen />Пояснительная записка (классы 71–76)</Button>
            <Button variant={doc === "vv" ? "default" : "outline"} onClick={() => setDoc(doc === "vv" ? null : "vv")}><BookOpen />Введение</Button>
            {doc && <Button variant="ghost" render={<a href={`/classifier/doc/${doc}`} target="_blank" rel="noreferrer" />}>Открыть в новой вкладке</Button>}
          </div>
          {doc && <iframe title="Классификатор ЕСКД" src={`/classifier/doc/${doc}`} className="h-[70vh] w-full rounded-lg border bg-background" />}
        </CardContent>
      </Card>
    </div>
  )
}
