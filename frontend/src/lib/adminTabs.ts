export const ADMIN_TABS: [string, string][] = [
  ["rules", "Проверки по стандартам"], ["custom", "Свои правила"], ["params", "Параметры"], ["equip", "Оборудование"], ["lists", "Справочники"],
  ["ex", "Исключения «не ошибка»"], ["users", "Пользователи"], ["stds", "Реестр стандартов"], ["cls", "Классификатор"], ["norms", "Нормативы"], ["review", "Отметки тестеров"], ["log", "Журнал действий"],
]

export const adminTabNow = (sp: URLSearchParams) =>
  sp.get("tab") || (() => { try { return localStorage.getItem("admin-tab") || "rules" } catch { return "rules" } })()
