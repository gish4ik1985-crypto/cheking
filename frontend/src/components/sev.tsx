import { AlertOctagon, AlertTriangle, Info } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import type { Sev } from "@/lib/types"

export const SEV_LABEL: Record<Sev, string> = { error: "Ошибка", warning: "Предупреждение", info: "Замечание" }
export const SEV_SHORT: Record<Sev, string> = { error: "Ошибка", warning: "Предупр.", info: "Замечание" }

export const sevMeta: Record<Sev, { label: string; icon: typeof Info; cls: string; bar: string; text: string }> = {
  error: { label: "Ошибка", icon: AlertOctagon, cls: "bg-[var(--sev-error-bg)] text-[var(--sev-error)] border-[var(--sev-error)]/25", bar: "bg-[var(--sev-error)]", text: "text-[var(--sev-error)]" },
  warning: { label: "Предупреждение", icon: AlertTriangle, cls: "bg-[var(--sev-warn-bg)] text-[var(--sev-warn)] border-[var(--sev-warn)]/25", bar: "bg-[var(--sev-warn)]", text: "text-[var(--sev-warn)]" },
  info: { label: "Замечание", icon: Info, cls: "bg-[var(--sev-info-bg)] text-[var(--sev-info)] border-[var(--sev-info)]/25", bar: "bg-[var(--sev-info)]", text: "text-[var(--sev-info)]" },
}

export function SevBadge({ sev, children }: { sev: Sev; children?: React.ReactNode }) {
  const m = sevMeta[sev]
  return (
    <Badge variant="outline" className={`gap-1 ${m.cls}`}>
      <m.icon className="size-3" />{children ?? m.label}
    </Badge>
  )
}

export function OkBadge({ children = "OK" }: { children?: React.ReactNode }) {
  return <Badge variant="outline" className="border-[var(--sev-ok)]/30 bg-[var(--sev-ok-bg)] text-[var(--sev-ok)]">{children}</Badge>
}

export function Counts({ e, w, i }: { e: number; w: number; i: number }) {
  return (
    <span className="inline-flex flex-wrap items-center gap-1">
      {e > 0 && <SevBadge sev="error">{e}</SevBadge>}
      {w > 0 && <SevBadge sev="warning">{w}</SevBadge>}
      {i > 0 && <SevBadge sev="info">{i}</SevBadge>}
      {e + w + i === 0 && <OkBadge>без замечаний</OkBadge>}
    </span>
  )
}
