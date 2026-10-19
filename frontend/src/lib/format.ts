export const num = (v: number | null | undefined) => (v === null || v === undefined ? "" : String(v).replace(".", ","))
export const signed = (v: number | null | undefined) =>
  v === null || v === undefined ? "" : (v > 0 ? "+" : "") + num(+v.toFixed(4))

export const KIND_RU: Record<string, string> = {
  linear: "линейный", diameter: "диаметр", radius: "радиус", thread: "резьба", chamfer: "фаска", angle: "угол",
  thickness: "толщина", sphere: "сфера", square: "квадрат", thread_other: "резьба", thread_tr: "резьба Tr", thread_g: "резьба G",
}

/** «20261015-094100-ab12cd» → «15.10.2026 09:41» */
export function jobWhen(id: string) {
  const m = /^(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})/.exec(id)
  return m ? `${m[3]}.${m[2]}.${m[1]} ${m[4]}:${m[5]}` : id
}

export const details = (d: unknown): string =>
  typeof d === "object" && d
    ? Object.entries(d as Record<string, unknown>).map(([k, v]) => k + ": " + (Array.isArray(v) ? v.join(", ") : v)).join("; ")
    : String(d ?? "")
