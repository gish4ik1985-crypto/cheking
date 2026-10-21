import { useCallback, useEffect, useMemo, useState } from "react"
import { useSearchParams } from "react-router-dom"
import { toast } from "sonner"
import { api, ApiError, errText } from "@/lib/api"
import { useAuth } from "@/lib/auth"
import { Button } from "@/components/ui/button"
import { Tabs, TabsContent } from "@/components/ui/tabs"
import { AdminContext, type AdminState, type RulesMap } from "./admin/context"
import RulesTab from "./admin/RulesTab"
import CustomTab from "./admin/CustomTab"
import EquipmentTab from "./admin/EquipmentTab"
import { StandardsTab } from "./admin/StandardsTab"
import { ClassifierTab } from "./admin/ClassifierTab"
import { ExceptionsTab, ListsTab, LogTab, NormsTab, ParamsTab, ReviewTab, UsersTab } from "./admin/OtherAdminTabs"

const clone = <T,>(o: T): T => JSON.parse(JSON.stringify(o))

export default function AdminPage() {
  const { isAdmin } = useAuth()
  const [sp, setSp] = useSearchParams()
  const [S, setS] = useState<AdminState | null>(null)
  const [rules, setRules] = useState<RulesMap>({})
  const [modules, setModules] = useState<Record<string, boolean>>({})
  const [params, setParams] = useState<Record<string, any>>({})
  const [lists, setLists] = useState<AdminState["lists"]>({ obsolete_standards: [] })
  const [orig, setOrig] = useState<string>("")
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [denied, setDenied] = useState(false)
  const [err, setErr] = useState("")

  const tab = sp.get("tab") || (() => { try { return localStorage.getItem("admin-tab") || "rules" } catch { return "rules" } })()
  const setTab = (t: string) => {
    setSp({ tab: t }, { replace: true })
    try { localStorage.setItem("admin-tab", t) } catch { /* без хранилища */ }
  }

  const load = useCallback(async () => {
    try {
      const j = await api<AdminState>("/api/admin/state")
      const r: RulesMap = {}
      for (const g of j.groups) for (const x of g.rules) r[x.code] = { enabled: x.enabled, severity: x.severity || "" }
      const m: Record<string, boolean> = {}
      for (const s of j.sections) if (s.module) m[s.key] = s.module.enabled
      setS(j); setRules(r); setModules(m); setParams(clone(j.params)); setLists(clone(j.lists))
      setOrig(JSON.stringify({ rules: r, params: j.params, lists: j.lists, modules: m }))
      setDenied(false)
    } catch (e) {
      if (e instanceof ApiError && e.status === 403) setDenied(true)
      else setErr(errText(e))
    }
  }, [])
  useEffect(() => { if (isAdmin) void load(); else setDenied(true) }, [isAdmin, load])

  const now = useMemo(() => JSON.stringify({ rules, params, lists, modules }), [rules, params, lists, modules])
  const dirty = !!S && now !== orig
  const changedCount = useMemo(() => {
    if (!orig) return 0
    const o = JSON.parse(orig)
    let n = 0
    for (const c in rules) if (o.rules[c] && (rules[c].enabled !== o.rules[c].enabled || rules[c].severity !== o.rules[c].severity)) n++
    for (const k in modules) if (modules[k] !== o.modules[k]) n++
    return n
  }, [rules, modules, orig])

  // предупреждение о несохранённых изменениях при закрытии вкладки
  useEffect(() => {
    const on = (e: BeforeUnloadEvent) => { if (dirty) { e.preventDefault(); e.returnValue = "" } }
    window.addEventListener("beforeunload", on)
    return () => window.removeEventListener("beforeunload", on)
  }, [dirty])

  const save = async () => {
    setSaving(true)
    try {
      await api("/api/admin/settings", { json: { rules, params, lists, modules } })
      setOrig(JSON.stringify({ rules, params, lists, modules }))
      setSaved(true)
      toast.success("Сохранено — настройки применяются ко всем отчётам")
      setTimeout(() => setSaved(false), 2200)
    } catch (e) { toast.error(errText(e)) }
    setSaving(false)
  }
  const cancel = () => {
    const o = JSON.parse(orig)
    setRules(o.rules); setParams(o.params); setLists(o.lists); setModules(o.modules)
  }

  if (denied) return (
    <div className="mx-auto max-w-lg p-8 text-center">
      <h1 className="mb-2 text-xl font-semibold">Нет доступа</h1>
      <p className="text-sm text-muted-foreground">Настройки и журнал доступны только администратору.</p>
    </div>
  )
  if (!S) return <div className="p-6 text-sm text-muted-foreground">{err || "Загрузка настроек…"}</div>

  return (
    <AdminContext.Provider value={{
      S, rules, setRules: f => setRules(f), modules, setModules: f => setModules(f), params, setParams: f => setParams(f),
      lists, setLists: f => setLists(f), reload: load, dirty,
    }}>
      <div className="mx-auto grid max-w-[1500px] gap-4 p-4 pb-24 md:p-6 md:pb-24">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Настройки проверки</h1>
          <p className="text-sm text-muted-foreground">Какие проверки выполнять и с какой важностью — для всех пользователей программы. Настройки сразу действуют на все отчёты, в том числе уже сохранённые.</p>
        </div>
        <Tabs value={tab} onValueChange={setTab}>
          <TabsContent value="rules" className="min-w-0 flex-1"><RulesTab /></TabsContent>
          <TabsContent value="custom" className="min-w-0 flex-1"><CustomTab /></TabsContent>
          <TabsContent value="params" className="min-w-0 flex-1"><ParamsTab /></TabsContent>
          <TabsContent value="equip" className="min-w-0 flex-1"><EquipmentTab /></TabsContent>
          <TabsContent value="lists" className="min-w-0 flex-1"><ListsTab /></TabsContent>
          <TabsContent value="ex" className="min-w-0 flex-1"><ExceptionsTab /></TabsContent>
          <TabsContent value="users" className="min-w-0 flex-1"><UsersTab /></TabsContent>
          <TabsContent value="stds" className="min-w-0 flex-1"><StandardsTab /></TabsContent>
          <TabsContent value="cls" className="min-w-0 flex-1"><ClassifierTab /></TabsContent>
          <TabsContent value="norms" className="min-w-0 flex-1"><NormsTab /></TabsContent>
          <TabsContent value="review" className="min-w-0 flex-1"><ReviewTab /></TabsContent>
          <TabsContent value="log" className="min-w-0 flex-1"><LogTab /></TabsContent>
        </Tabs>
      </div>

      {(dirty || saved) && (
        <div className="fixed inset-x-0 bottom-0 z-30 flex items-center gap-3 border-t bg-background/95 px-4 py-3 shadow-lg backdrop-blur md:left-[var(--sidebar-width)]">
          <span className="text-sm">
            {saved && !dirty ? "Сохранено — настройки применяются ко всем отчётам"
              : changedCount ? `Изменено проверок: ${changedCount}${JSON.stringify({ params, lists }) !== JSON.stringify({ params: JSON.parse(orig).params, lists: JSON.parse(orig).lists }) ? " и параметры" : ""}` : "Изменены параметры"}
          </span>
          <span className="flex-1" />
          <Button variant="outline" onClick={cancel} disabled={!dirty}>Отменить</Button>
          <Button onClick={() => void save()} disabled={saving || !dirty}>Сохранить</Button>
        </div>
      )}
    </AdminContext.Provider>
  )
}
