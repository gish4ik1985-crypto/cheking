// Обёртка над fetch для API программы: JSON, ошибки с текстом сервера, событие «нужен вход».
export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

export const AUTH_EVENT = "checking:auth-required"

interface Opts {
  method?: string
  json?: unknown
  form?: FormData
  quiet?: boolean // не отправлять событие «нужен вход» на 401
}

export async function api<T = any>(url: string, o: Opts = {}): Promise<T> {
  const init: RequestInit = { method: o.method ?? (o.json !== undefined || o.form ? "POST" : "GET"), credentials: "same-origin" }
  if (o.json !== undefined) {
    init.headers = { "Content-Type": "application/json" }
    init.body = JSON.stringify(o.json)
  } else if (o.form) init.body = o.form
  const r = await fetch(url, init)
  let data: any = null
  try { data = await r.json() } catch { /* пустой ответ */ }
  if (!r.ok) {
    if (r.status === 401 && !o.quiet) window.dispatchEvent(new Event(AUTH_EVENT))
    throw new ApiError(r.status, (data && (data.error || data.message)) || r.statusText || "Ошибка запроса")
  }
  return data as T
}

export const errText = (e: unknown) => (e instanceof Error ? e.message : String(e))
