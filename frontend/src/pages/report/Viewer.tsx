import { forwardRef, useCallback, useEffect, useImperativeHandle, useLayoutEffect, useRef, useState } from "react"
import { Maximize2, Minus, Plus, ScanSearch, ChevronLeft, ChevronRight, MousePointerClick } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import type { DocResult, FbEntry, Finding } from "@/lib/types"
import { sevMeta } from "@/components/sev"

export type NFinding = Finding & { n: number }

export interface ViewerHandle {
  step: (dir: 1 | -1) => void
  zoomBy: (k: number) => void
  reset: () => void
}

interface Props {
  doc: DocResult
  jobId: string
  findings: NFinding[]
  selected: number | null
  onSelect: (n: number | null) => void
  pick: boolean
  onPick: (page: number, point: [number, number]) => void
  missed: FbEntry[]
}

const clamp = (v: number, a: number, b: number) => Math.max(a, Math.min(b, v))

const Viewer = forwardRef<ViewerHandle, Props>(function Viewer({ doc, jobId, findings, selected, onSelect, pick, onPick, missed }, ref) {
  const scroller = useRef<HTMLDivElement>(null)
  const inner = useRef<HTMLDivElement>(null)
  const [zoom, setZoom] = useState(1)
  const zoomRef = useRef(1)
  const saved = useRef<Record<string, { zoom: number; left: number; top: number }>>({})
  const key = jobId + ":" + doc.id
  const pages = doc.pages.filter(p => p.image)
  const located = findings.filter(f => f.bbox)

  const baseW = () => { const sc = scroller.current; return sc ? Math.max(200, sc.clientWidth - 16) : 800 }
  const applyWidth = useCallback((z: number) => { if (inner.current) inner.current.style.width = Math.round(baseW() * z) + "px" }, [])

  const setZ = useCallback((z: number, mx?: number, my?: number) => {
    const sc = scroller.current, el = inner.current
    if (!sc || !el) return
    mx ??= sc.clientWidth / 2
    my ??= sc.clientHeight / 2
    const fx = (sc.scrollLeft + mx - el.offsetLeft) / el.offsetWidth
    const fy = (sc.scrollTop + my - el.offsetTop) / el.offsetHeight
    const nz = clamp(z, 0.15, 12)
    zoomRef.current = nz
    setZoom(nz)
    applyWidth(nz)
    sc.scrollLeft = fx * el.offsetWidth + el.offsetLeft - mx
    sc.scrollTop = fy * el.offsetHeight + el.offsetTop - my
  }, [applyWidth])

  // при смене документа возвращаем сохранённый масштаб и положение
  useLayoutEffect(() => {
    const st = saved.current[key] ?? { zoom: 1, left: 0, top: 0 }
    zoomRef.current = st.zoom
    setZoom(st.zoom)
    applyWidth(st.zoom)
    const sc = scroller.current
    if (sc) { sc.scrollLeft = st.left; sc.scrollTop = st.top }
    return () => {
      const s = scroller.current
      if (s) saved.current[key] = { zoom: zoomRef.current, left: s.scrollLeft, top: s.scrollTop }
    }
  }, [key, applyWidth])

  useEffect(() => {
    const on = () => applyWidth(zoomRef.current)
    window.addEventListener("resize", on)
    const ro = new ResizeObserver(on)
    if (scroller.current) ro.observe(scroller.current)
    return () => { window.removeEventListener("resize", on); ro.disconnect() }
  }, [applyWidth])

  // колесо — масштаб вокруг курсора
  useEffect(() => {
    const sc = scroller.current
    if (!sc) return
    const wheel = (ev: WheelEvent) => {
      ev.preventDefault()
      const r = sc.getBoundingClientRect()
      setZ(zoomRef.current * Math.exp(-ev.deltaY * 0.0016), ev.clientX - r.left, ev.clientY - r.top)
    }
    sc.addEventListener("wheel", wheel, { passive: false })
    return () => sc.removeEventListener("wheel", wheel)
  }, [setZ, key])

  // перетаскивание — сдвиг
  const drag = useRef<{ x: number; y: number; l: number; t: number; moved: boolean } | null>(null)
  const justDragged = useRef(false)
  const onDown = (ev: React.MouseEvent) => {
    const sc = scroller.current
    if (!sc || ev.button !== 0 || (ev.target as HTMLElement).closest("[data-mark]")) return
    drag.current = { x: ev.clientX, y: ev.clientY, l: sc.scrollLeft, t: sc.scrollTop, moved: false }
  }
  useEffect(() => {
    const move = (ev: MouseEvent) => {
      const d = drag.current, sc = scroller.current
      if (!d || !sc) return
      const dx = ev.clientX - d.x, dy = ev.clientY - d.y
      if (!d.moved && Math.hypot(dx, dy) > 4) { d.moved = true; sc.style.cursor = "grabbing" }
      if (d.moved) { sc.scrollLeft = d.l - dx; sc.scrollTop = d.t - dy }
    }
    const up = () => {
      const d = drag.current, sc = scroller.current
      if (d?.moved) { justDragged.current = true; setTimeout(() => { justDragged.current = false }, 0) }
      if (sc) sc.style.cursor = ""
      drag.current = null
    }
    window.addEventListener("mousemove", move)
    window.addEventListener("mouseup", up)
    return () => { window.removeEventListener("mousemove", move); window.removeEventListener("mouseup", up) }
  }, [])

  const fitAll = () => {
    const sc = scroller.current, p = pages[0]
    if (!sc || !p) return
    setZ(Math.min(1, (sc.clientHeight - 20) / ((baseW() * p.height) / p.width)))
    sc.scrollLeft = 0; sc.scrollTop = 0
  }
  const reset = () => { setZ(1); const sc = scroller.current; if (sc) { sc.scrollLeft = 0; sc.scrollTop = 0 } }

  const focusMark = useCallback((n: number) => {
    const sc = scroller.current
    const m = inner.current?.querySelector<HTMLElement>(`[data-mark="${n}"]`)
    if (!m || !sc) return
    const mr = m.getBoundingClientRect()
    if (mr.width < 70) setZ(Math.min((zoomRef.current * 110) / Math.max(mr.width, 8), Math.max(zoomRef.current, 4)), sc.clientWidth / 2, sc.clientHeight / 2)
    const r2 = m.getBoundingClientRect(), sr = sc.getBoundingClientRect()
    sc.scrollTo({ left: sc.scrollLeft + (r2.left + r2.width / 2) - (sr.left + sr.width / 2), top: sc.scrollTop + (r2.top + r2.height / 2) - (sr.top + sr.height / 2) })
  }, [setZ])

  const step = (dir: 1 | -1) => {
    if (!located.length) return
    let i = located.findIndex(f => f.n === selected)
    i = i < 0 ? (dir > 0 ? 0 : located.length - 1) : (i + dir + located.length) % located.length
    onSelect(located[i].n)
    requestAnimationFrame(() => focusMark(located[i].n))
  }
  useImperativeHandle(ref, () => ({ step, zoomBy: k => setZ(zoomRef.current * k), reset }))

  // выбор замечания в списке справа — показать метку
  const lastFocus = useRef<number | null>(null)
  useEffect(() => {
    if (selected !== null && selected !== lastFocus.current) focusMark(selected)
    lastFocus.current = selected
  }, [selected, focusMark])

  const cur = located.findIndex(f => f.n === selected)

  return (
    <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden rounded-xl border bg-card">
      <div className="flex flex-wrap items-center gap-1 border-b px-2 py-1.5">
        <Tooltip><TooltipTrigger render={<Button variant="ghost" size="icon-sm" onClick={() => setZ(zoom / 1.3)} aria-label="Уменьшить" />}><Minus /></TooltipTrigger><TooltipContent>Уменьшить (−)</TooltipContent></Tooltip>
        <span className="w-12 text-center text-xs tabular-nums text-muted-foreground">{Math.round(zoom * 100)}%</span>
        <Tooltip><TooltipTrigger render={<Button variant="ghost" size="icon-sm" onClick={() => setZ(zoom * 1.3)} aria-label="Увеличить" />}><Plus /></TooltipTrigger><TooltipContent>Увеличить (+)</TooltipContent></Tooltip>
        <Tooltip><TooltipTrigger render={<Button variant="ghost" size="sm" onClick={reset} />}><ScanSearch />По ширине</TooltipTrigger><TooltipContent>Масштаб по ширине окна (0)</TooltipContent></Tooltip>
        <Tooltip><TooltipTrigger render={<Button variant="ghost" size="sm" onClick={fitAll} />}><Maximize2 />Лист целиком</TooltipTrigger><TooltipContent>Лист целиком</TooltipContent></Tooltip>
        <span className="mx-1 h-5 w-px bg-border" />
        <Tooltip><TooltipTrigger render={<Button variant="ghost" size="icon-sm" onClick={() => step(-1)} aria-label="Предыдущее замечание" />}><ChevronLeft /></TooltipTrigger><TooltipContent>Предыдущее замечание (K)</TooltipContent></Tooltip>
        <span className="w-12 text-center text-xs tabular-nums text-muted-foreground">{located.length ? `${cur >= 0 ? cur + 1 : "–"}/${located.length}` : "0"}</span>
        <Tooltip><TooltipTrigger render={<Button variant="ghost" size="icon-sm" onClick={() => step(1)} aria-label="Следующее замечание" />}><ChevronRight /></TooltipTrigger><TooltipContent>Следующее замечание (J)</TooltipContent></Tooltip>
        <span className="ml-auto hidden text-xs text-muted-foreground xl:inline">Колесо — масштаб · перетаскивание — сдвиг</span>
      </div>
      {pick && (
        <div className="flex items-center gap-2 border-b bg-[var(--sev-warn-bg)] px-3 py-1.5 text-sm text-[var(--sev-warn)]">
          <MousePointerClick className="size-4" />Нажмите на лист там, где программа должна была найти ошибку (Esc — отмена)
        </div>
      )}
      <div ref={scroller} onMouseDown={onDown} className="relative min-h-0 flex-1 cursor-grab overflow-auto bg-muted/50 p-2"
        onClickCapture={e => { if (justDragged.current) { e.stopPropagation(); e.preventDefault() } }}>
        <div ref={inner} className={`relative mx-auto grid gap-3 ${pick ? "cursor-crosshair" : ""}`}>
          {pages.map(p => (
            <div key={p.number} className="relative overflow-hidden rounded bg-white shadow-sm ring-1 ring-black/10"
              onClick={ev => {
                if (!pick) return
                const img = (ev.currentTarget as HTMLElement).querySelector("img")!
                const rc = img.getBoundingClientRect()
                onPick(p.number, [+(((ev.clientX - rc.left) / rc.width) * p.width).toFixed(1), +(((ev.clientY - rc.top) / rc.height) * p.height).toFixed(1)])
              }}>
              <img src={p.image} alt={`Лист ${p.number + 1}`} draggable={false} className="block w-full select-none" />
              <span className="absolute left-2 top-2 rounded bg-black/55 px-1.5 py-0.5 text-[11px] text-white">лист {p.number + 1}</span>
              {missed.filter(e => e.page === p.number && e.point).map(e => (
                <span key={e.id} title={"Пропуск: " + (e.comment ?? "")} className="absolute size-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-white bg-fuchsia-600 shadow"
                  style={{ left: `${(e.point![0] / p.width) * 100}%`, top: `${(e.point![1] / p.height) * 100}%` }} />
              ))}
              {findings.filter(f => f.page === p.number && f.bbox).map(f => {
                const pad = 1.2
                const [x0, y0, x1, y1] = f.bbox!
                const m = sevMeta[f.severity]
                const active = selected === f.n
                return (
                  <div key={f.n} data-mark={f.n} title={f.message} onClick={ev => { ev.stopPropagation(); onSelect(f.n) }}
                    className={`absolute cursor-pointer rounded-[3px] border-2 border-current transition ${m.text} ${active ? "z-10 bg-current/15 ring-4 ring-primary/40" : "hover:bg-current/10"}`}
                    style={{ left: `${((x0 - pad) / p.width) * 100}%`, top: `${((y0 - pad) / p.height) * 100}%`, width: `${((x1 - x0 + 2 * pad) / p.width) * 100}%`, height: `${((y1 - y0 + 2 * pad) / p.height) * 100}%` }}>
                    <span className={`absolute -left-2 -top-3 grid min-w-5 place-items-center rounded-full px-1 text-[11px] font-semibold leading-5 text-white ${m.bar}`}>{f.n}</span>
                  </div>
                )
              })}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
})

export default Viewer
