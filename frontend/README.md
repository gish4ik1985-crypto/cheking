# Интерфейс «Проверки чертежей» (shadcn/ui)

React + TypeScript + Tailwind 4 + shadcn/ui (стиль base-nova, Base UI). Данные — по API Flask-приложения (`../app.py`).

```bash
npm install
npm run dev     # http://localhost:5173, API — http://127.0.0.1:8765 (переменная CHECKING_API)
npm run build   # frontend/dist — его раздаёт Flask
```

Структура: `src/pages` — страницы (`LoginPage`, `UploadPage`, `ReportPage`, `AdminPage`, `ProfilePage`), `src/pages/report` — лист и вкладки отчёта,
`src/pages/admin` — вкладки настроек, `src/components/ui` — компоненты shadcn, `src/lib` — API, вход, тема.
Добавить компонент shadcn: `npx shadcn@latest add <имя>`.
