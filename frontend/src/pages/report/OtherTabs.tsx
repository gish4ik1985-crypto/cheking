import { Trash2 } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { KIND_RU, num, signed } from "@/lib/format"
import { useAuth } from "@/lib/auth"
import type { DocResult, FbEntry } from "@/lib/types"

const Empty = ({ children }: { children: React.ReactNode }) => (
  <p className="rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">{children}</p>
)

export function DimsTab({ doc, onWrong }: { doc: DocResult; onWrong: (raw: string) => void }) {
  if (!doc.dims.length) return <Empty>Размеры не извлечены (для .cdw/.dft без САПР — только основная надпись и ТТ).</Empty>
  return (
    <Card className="overflow-hidden">
      <Table>
        <TableHeader>
          <TableRow><TableHead>Размер</TableHead><TableHead>Тип</TableHead><TableHead>Номинал</TableHead><TableHead>Поле</TableHead>
            <TableHead>Верх.</TableHead><TableHead>Ниж.</TableHead><TableHead>Прим.</TableHead><TableHead /></TableRow>
        </TableHeader>
        <TableBody>
          {doc.dims.map((x, i) => (
            <TableRow key={i}>
              <TableCell className="font-mono">{x.raw}</TableCell>
              <TableCell>{KIND_RU[x.kind] || x.kind}</TableCell>
              <TableCell>{num(x.nominal)}</TableCell>
              <TableCell>{x.field || x.fit || ""}</TableCell>
              <TableCell>{signed(x.upper)}</TableCell>
              <TableCell>{signed(x.lower)}</TableCell>
              <TableCell className="whitespace-normal text-muted-foreground">{[x.reference ? "справочный" : "", x.count ? x.count + " шт." : ""].filter(Boolean).join(", ")}</TableCell>
              <TableCell><Button variant="link" size="xs" title="Программа прочитала размер неправильно" onClick={() => onWrong(x.raw)}>не так</Button></TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Card>
  )
}

export function LimitsTab({ doc }: { doc: DocResult }) {
  if (!doc.limits.length) return <Empty>На чертеже нет размеров с полями допусков или отклонениями.</Empty>
  return (
    <Card className="overflow-hidden">
      <Table>
        <TableHeader><TableRow><TableHead>Размер</TableHead><TableHead>Поле / посадка</TableHead><TableHead>Предельные отклонения (ГОСТ 25346)</TableHead><TableHead>Квалитет</TableHead></TableRow></TableHeader>
        <TableBody>
          {doc.limits.map((x, i) => (
            <TableRow key={i}><TableCell className="font-mono">{x.dim}</TableCell><TableCell>{x.code || "числом"}</TableCell><TableCell>{x.limits}</TableCell><TableCell>{x.grade ? "IT" + x.grade : ""}</TableCell></TableRow>
          ))}
        </TableBody>
      </Table>
    </Card>
  )
}

export function TitleTab({ doc }: { doc: DocResult }) {
  const t = doc.title
  const rows: [string, string | undefined][] = [
    ["Обозначение", t.designation], ["Наименование", t.name], ["Материал", t.material], ["Масса", t.mass], ["Масштаб", t.scale],
    ["Формат", t.format], ["Листов", t.sheets], ["Организация", t.organization],
    ...Object.entries(t.people || {}),
    ...(t.changes || []).map(c => ["Изменение " + c.num, [c.sheet, c.doc, c.date].filter(Boolean).join(" · ")] as [string, string]),
  ]
  return (
    <div className="grid gap-3">
      {!t.found && <Empty>Основная надпись по форме 1 не распознана — поля могут быть пустыми.</Empty>}
      <Card className="overflow-hidden">
        <Table><TableBody>
          {rows.map(([k, v], i) => (
            <TableRow key={i}><TableCell className="w-2/5 font-medium text-muted-foreground">{k}</TableCell><TableCell className="whitespace-normal">{v || "—"}</TableCell></TableRow>
          ))}
        </TableBody></Table>
      </Card>
    </div>
  )
}

export function TtTab({ doc }: { doc: DocResult }) {
  const rough = (doc.roughness || []).map(r => `${r.param} ${num(r.value)}${r.general ? " (общая)" : ""}`).join(", ")
  return (
    <div className="grid gap-3">
      {doc.tt.length ? (
        <Card className="p-4"><ol className="grid list-decimal gap-1.5 pl-5 text-sm">{doc.tt.map((x, i) => <li key={i}>{x}</li>)}</ol></Card>
      ) : <Empty>ТТ не найдены</Empty>}
      <p className="text-sm text-muted-foreground">Шероховатость на листе: {rough || "не указана"}</p>
    </div>
  )
}

export function OpsTab({ doc }: { doc: DocResult }) {
  const ops: any[] = doc.facts?.process?.operations || []
  if (!ops.length) return <Empty>Операции не распознаны: пришлите образец документа, чтобы научить программу его форме.</Empty>
  return (
    <Card className="overflow-hidden">
      <Table>
        <TableHeader><TableRow><TableHead>№</TableHead><TableHead>Операция</TableHead><TableHead>Оборудование</TableHead><TableHead>Строка документа</TableHead></TableRow></TableHeader>
        <TableBody>
          {ops.map((o, i) => (
            <TableRow key={i}><TableCell className="font-mono">{o.no || "—"}</TableCell><TableCell className="whitespace-normal">{o.name}</TableCell><TableCell>{o.equipment || ""}</TableCell><TableCell className="whitespace-normal text-xs text-muted-foreground">{o.line}</TableCell></TableRow>
          ))}
        </TableBody>
      </Table>
    </Card>
  )
}

export function RowsTab({ doc }: { doc: DocResult }) {
  const rows: any[] = doc.facts?.spec_rows || []
  if (!rows.length) return <Empty>Строки таблицы не распознаны.</Empty>
  return (
    <Card className="overflow-hidden">
      <Table>
        <TableHeader><TableRow><TableHead>Раздел</TableHead><TableHead>Поз.</TableHead><TableHead>Обозначение</TableHead><TableHead>Наименование</TableHead><TableHead>Кол.</TableHead><TableHead>Прим.</TableHead></TableRow></TableHeader>
        <TableBody>
          {rows.map((r, i) => (
            <TableRow key={i}>
              <TableCell className="text-xs text-muted-foreground">{r.section || ""}</TableCell><TableCell className="font-mono">{r.pos || ""}</TableCell>
              <TableCell className="font-mono">{r.designation || ""}</TableCell><TableCell className="whitespace-normal">{r.name || ""}</TableCell>
              <TableCell>{r.qty == null ? "" : num(r.qty)}{r.unit ? " " + r.unit : ""}</TableCell><TableCell className="whitespace-normal text-xs">{r.note || ""}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Card>
  )
}

const TYPE: Record<string, string> = { finding: "Замечание", missed: "Пропуск", parse: "Разбор", comment: "Комментарий" }
const VERD: Record<string, string> = { ok: "верно", false: "ложное", inexact: "неточно" }

export function FbTab({ doc, fb, onDelete }: { doc: DocResult; fb: FbEntry[]; onDelete: (id: string) => void }) {
  const { me, isAdmin } = useAuth()
  const list = fb.filter(e => e.doc === doc.id)
  return (
    <div className="grid gap-3">
      <p className="text-sm text-muted-foreground">
        Ваши отметки по этому чертежу{isAdmin ? " (администратор видит отметки всех)" : ""}. Отмечайте замечания кнопками «верно / ложное / неточно», а пропуски — кнопкой «Программа не заметила».
      </p>
      {list.length === 0 ? <Empty>Отметок пока нет</Empty> : (
        <Card className="overflow-hidden">
          <Table>
            <TableHeader><TableRow><TableHead>Тип</TableHead><TableHead>Кто</TableHead><TableHead>Что</TableHead><TableHead /></TableRow></TableHeader>
            <TableBody>
              {list.map(e => (
                <TableRow key={e.id}>
                  <TableCell><Badge variant="secondary">{TYPE[e.type]}{e.verdict ? " · " + VERD[e.verdict] : ""}</Badge></TableCell>
                  <TableCell>{e.user}</TableCell>
                  <TableCell className="whitespace-normal text-sm">{[e.code, e.message || e.dim, e.group, e.expected ? "→ " + e.expected : "", e.comment].filter(Boolean).join(" · ")}</TableCell>
                  <TableCell>{(e.user === me?.name || isAdmin) && <Button variant="ghost" size="icon-xs" aria-label="Удалить" onClick={() => onDelete(e.id)}><Trash2 /></Button>}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Card>
      )}
    </div>
  )
}
