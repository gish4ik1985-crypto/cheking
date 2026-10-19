// Типы ответов API (описаны по реальным данным; лишние поля допускаются).
export type Sev = "error" | "warning" | "info"

export interface Me {
  name: string
  role: "admin" | "user"
  created: string
  default_password?: boolean
  version?: string
}

export interface Finding {
  code: string
  severity: Sev
  category: string
  message: string
  standard?: string
  page?: number | null
  bbox?: [number, number, number, number] | null
  rule_id?: string
  rule_scope?: string
  [k: string]: any
}

export interface Page {
  number: number
  image?: string
  width: number
  height: number
}

export interface Title {
  designation?: string
  name?: string
  material?: string
  mass?: string
  scale?: string
  format?: string
  sheets?: string
  organization?: string
  people?: Record<string, string>
  changes?: { num: string; sheet?: string; doc?: string; date?: string }[]
  found?: boolean
}

export interface Dim {
  raw: string
  kind: string
  nominal: number | null
  field?: string | null
  fit?: string | null
  upper?: number | null
  lower?: number | null
  reference?: string
  count?: number | null
}

export interface DocResult {
  id: number
  file: string
  kind: string
  ocr?: boolean
  error?: string
  sheets?: string
  pages: Page[]
  title: Title
  dims: Dim[]
  tt: string[]
  roughness?: { param: string; value: number; general?: boolean }[]
  limits: { dim: string; code?: string; limits: string; grade?: number }[]
  facts?: Record<string, any>
  findings: Finding[]
  suppressed?: Finding[]
  welds?: { raw: string }[]
  dxf?: { name: string; size: [number, number] }
  counts: Record<Sev, number>
}

export interface CompRow {
  pos: string
  designation: string
  sku: string
  name: string
  section: string
  status: "ok" | "warnings" | "errors" | "missing" | "not_required"
  need?: boolean
  errors?: number
  file?: string
  doc_id: number | null
}

export interface Completeness {
  stats: { missing: number; errors: number; warnings: number; ok: number }
  rows: CompRow[]
  extra: { designation: string; file: string }[]
}

export interface JobFull {
  state: "running" | "done" | "error"
  done: number
  total: number
  current?: string
  error?: string
  warnings?: string[]
  spec?: { name: string; items: number }
  results?: DocResult[]
  completeness?: Completeness | null
}

export interface FbEntry {
  id: string
  type: "finding" | "missed" | "parse" | "comment"
  doc: number
  user: string
  ts: string
  verdict?: "ok" | "false" | "inexact"
  code?: string
  message?: string
  comment?: string
  expected?: string
  dim?: string
  group?: string
  page?: number
  point?: [number, number]
  designation?: string
  file?: string
}

export interface HistoryItem { id: string; owner: string | null; count: number; errors: number; warnings: number }
