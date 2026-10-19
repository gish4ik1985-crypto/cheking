import { createContext, useContext } from "react"
import type { Sev } from "@/lib/types"

export interface RuleView {
  code: string
  text: string
  enabled: boolean
  severity: string
  typical: Sev
  default: boolean
  rev?: number
  doc?: { what?: string; how?: string; example?: string; skip?: string; params?: string } | null
}
export interface GroupView {
  key: string
  title: string
  standards: string
  description: string
  section: string
  locked?: boolean
  clauses?: [string, string, string][]
  rules: RuleView[]
}
export interface SectionView { key: string; title: string; module?: { enabled: boolean; default: boolean; descr: string } }
export interface StdEntry { key: string; label: string; direct: { code: string; clauses: string[] }[]; related: string[]; groups: string[] }

export interface AdminState {
  auth: { user: string }
  groups: GroupView[]
  sections: SectionView[]
  standards: StdEntry[]
  params: Record<string, any>
  custom_rules: any[]
  custom_meta: Record<string, Record<string, string>>
  defaults: Record<string, any>
  lists: { org_codes?: string[]; general_tolerance_refs?: string[]; obsolete_standards: { old: string; new: string }[] }
  default_obsolete: { old: string; new: string }[]
}

export type RulesMap = Record<string, { enabled: boolean; severity: string }>

export interface AdminCtx {
  S: AdminState
  rules: RulesMap
  setRules: (f: (r: RulesMap) => RulesMap) => void
  modules: Record<string, boolean>
  setModules: (f: (m: Record<string, boolean>) => Record<string, boolean>) => void
  params: Record<string, any>
  setParams: (f: (p: Record<string, any>) => Record<string, any>) => void
  lists: AdminState["lists"]
  setLists: (f: (l: AdminState["lists"]) => AdminState["lists"]) => void
  reload: () => Promise<void>
  dirty: boolean
}

export const AdminContext = createContext<AdminCtx | null>(null)
export const useAdmin = () => {
  const c = useContext(AdminContext)
  if (!c) throw new Error("AdminContext")
  return c
}
