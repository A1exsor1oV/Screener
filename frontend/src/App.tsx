import { useEffect, useMemo, useRef, useState } from "react";
import type { ScreenRow, ColumnKey } from "./types";
import { DEFAULT_COLUMNS, COLUMN_LABELS } from "./columns";
import {
  DndContext,
  closestCenter,
  PointerSensor,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import {
  SortableContext,
  arrayMove,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";

type IntervalMode = "3s" | "10m";
const API = (import.meta as any).env.VITE_API_URL ?? "http://localhost:8000";

export default function App() {
  const [rows, setRows] = useState<ScreenRow[]>([]);
  const [tickers, setTickers] = useState<string[]>(() =>
    JSON.parse(localStorage.getItem("tickers") || '["SBER","YNDX"]'),
  );
  const [columns, setColumns] = useState<ColumnKey[]>(() =>
    JSON.parse(
      localStorage.getItem("columns") || JSON.stringify(DEFAULT_COLUMNS),
    ),
  );
  const [hidden, setHidden] = useState<Set<ColumnKey>>(
    () => new Set(JSON.parse(localStorage.getItem("hidden") || "[]")),
  );
  const [mode, setMode] = useState<IntervalMode>(
    () => (localStorage.getItem("mode") as IntervalMode) || "3s",
  );
  const timerRef = useRef<number | null>(null);
  const sensors = useSensors(useSensor(PointerSensor));

  const visibleColumns = useMemo(
    () => columns.filter((c) => !hidden.has(c)),
    [columns, hidden],
  );
  const pollMs = mode === "3s" ? 3000 : 10 * 60 * 1000;

  async function load() {
    const q = new URLSearchParams();
    tickers.forEach((t) => q.append("tickers", t));
    const res = await fetch(`${API}/screen?${q.toString()}`);
    const data: ScreenRow[] = await res.json();
    setRows(data);
  }

  useEffect(() => {
    localStorage.setItem("tickers", JSON.stringify(tickers));
    localStorage.setItem("columns", JSON.stringify(columns));
    localStorage.setItem("hidden", JSON.stringify(Array.from(hidden)));
    localStorage.setItem("mode", mode);
  }, [tickers, columns, hidden, mode]);

  useEffect(() => {
    load();
    if (timerRef.current) window.clearInterval(timerRef.current);
    timerRef.current = window.setInterval(load, pollMs);
    return () => {
      if (timerRef.current) window.clearInterval(timerRef.current);
    };
  }, [tickers, pollMs]);

  return (
    <div className="min-h-screen">
      <div className="mx-auto max-w-7xl px-3 sm:px-4 md:px-5 py-6">
        <TopBar />
        <div className="mt-4 grid gap-4">
          <TradeBar />
          <section className="panel p-3 md:p-4">
            <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-2 mb-3">
              <div className="text-lg font-semibold">Котировки</div>
              <div className="flex flex-wrap items-center gap-2 hint text-sm">
                обновление: {mode === "3s" ? "каждые 3 сек" : "каждые 10 мин"}
                <span className="badge">Акции</span>
              </div>
            </div>
            {/* Панель действий */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2 mb-3">
              <ColumnsButton
                columns={columns}
                hidden={hidden}
                setColumns={setColumns}
                setHidden={setHidden}
                sensors={sensors}
              />
              <TickerSelect tickers={tickers} onChange={setTickers} />
              <div className="sm:col-span-2 lg:col-span-1 sm:justify-self-end">
                <IntervalToggle mode={mode} onChange={setMode} />
              </div>
            </div>
            {/* Таблица для md+ */}
            <div className="table-wrap hidden md:block">
              <table className="table">
                <thead>
                  <tr>
                    {visibleColumns.map((col, i) => (
                      <th
                        key={col}
                        className={
                          i === 0
                            ? "sticky left-0 z-[2] bg-[#101319]"
                            : undefined
                        }
                      >
                        {COLUMN_LABELS[col]}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r, idx) => (
                    <tr key={idx}>
                      {visibleColumns.map((col, i) => (
                        <td
                          key={col}
                          className={
                            "tabular-nums " +
                            (i === 0
                              ? "sticky left-0 z-[1] bg-[#0e1116]"
                              : "")
                          }
                        >
                          {renderCell(r, col)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
              {/* Мобильные карточки */}
            <div className="grid gap-2 md:hidden">
              {rows.map((r, idx) => (
                <MobileRowCard key={idx} row={r} columns={visibleColumns} />
              ))}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}

// ---- моб. карточка строки ----
function MobileRowCard({
  row,
  columns,
}: {
  row: ScreenRow;
  columns: ColumnKey[];
}) {
  const titleKey = columns.find((c) => c === "aktsiya") ?? columns[0];
  const subKey = columns.find((c) => c === "fyuchers") ?? columns[1] ?? columns[0];
  const rest = columns.filter((c) => c !== titleKey && c !== subKey);
  return (
    <article className="card">
      <div className="flex items-baseline justify-between">
        <div className="text-base font-semibold">{renderCell(row, titleKey)}</div>
        <div className="badge">
          {COLUMN_LABELS[subKey]}: {renderCell(row, subKey)}
        </div>
      </div>
      <div className="mt-2 mobile-grid">
        {rest.map((k) => (
          <div key={k} className="kv">
            <div className="kv-k">{COLUMN_LABELS[k]}</div>
            <div className="kv-v tabular-nums">{renderCell(row, k)}</div>
          </div>
        ))}
      </div>
    </article>
  );
}

function TopBar() {
  return (
    <header className="flex items-center justify-between mb-2">
      <div className="text-xl font-semibold">ExoHuman Trade</div>
      <div className="hint">MVP • demo feed</div>
    </header>
  );
}

function TradeBar() {
  return (
    <div className="panel p-4 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-12 gap-3">
      <input
        className="input sm:col-span-1 lg:col-span-3"
        placeholder="SBER"
        defaultValue="SBER"
      />
      <select className="input sm:col-span-1 lg:col-span-2">
        <option>Buy</option>
        <option>Sell</option>
      </select>
      <input className="input sm:col-span-1 lg:col-span-2" defaultValue={1} />
      <input
        className="input sm:col-span-1 lg:col-span-3"
        placeholder="Limit price (опц.)"
      />
      <div className="lg:col-span-12">
        <button className="btn btn-primary w-full">Отправить</button>
      </div>
    </div>
  );
}

function IntervalToggle({
  mode,
  onChange,
}: {
  mode: "3s" | "10m";
  onChange: (m: any) => void;
}) {
  return (
    <div className="flex items-center gap-2">
      <button
        className={`btn ${mode === "3s" ? "ring-1 ring-[--accent]" : ""}`}
        onClick={() => onChange("3s")}
      >
        3 сек
      </button>
      <button
        className={`btn ${mode === "10m" ? "ring-1 ring-[--accent]" : ""}`}
        onClick={() => onChange("10m")}
      >
        10 мин
      </button>
    </div>
  );
}

function renderCell(r: ScreenRow, col: ColumnKey) {
  const v = (r as any)[col];
  if (v == null) return "—";
  if (typeof v === "number") return v.toFixed(2);
  if (col === "div_ex_date") return new Date(v).toLocaleDateString();
  if (col === "has_div_before_exp") return v ? "Да" : "Нет";
  return String(v);
}

function TickerSelect({
  tickers,
  onChange,
}: {
  tickers: string[];
  onChange: (v: string[]) => void;
}) {
  const ALL = ["SBER", "YNDX"]; // можно расширить
  return (
    <div className="relative">
      <details>
        <summary className="btn">Акции</summary>
        <div className="absolute z-10 mt-2 panel-soft p-2">
          {ALL.map((t) => {
            const checked = tickers.includes(t);
            return (
              <label key={t} className="flex items-center gap-2 px-2 py-1">
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={(e) => {
                    if (e.target.checked) onChange([...tickers, t]);
                    else onChange(tickers.filter((x) => x !== t));
                  }}
                />
                <span>{t}</span>
              </label>
            );
          })}
        </div>
      </details>
    </div>
  );
}

function ColumnsButton({
  columns,
  hidden,
  setColumns,
  setHidden,
  sensors,
}: {
  columns: ColumnKey[];
  hidden: Set<ColumnKey>;
  setColumns: (v: ColumnKey[]) => void;
  setHidden: (v: Set<ColumnKey>) => void;
  sensors: any;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="relative">
      <button className="btn" onClick={() => setOpen((v) => !v)}>
        Столбцы
      </button>
      {open && (
        <div className="absolute z-10 mt-2 w-96 panel-soft p-3 shadow-xl">
          <DndContext
            sensors={sensors}
            collisionDetection={closestCenter}
            onDragEnd={(e) => {
              const { active, over } = e;
              if (over && active.id !== over.id) {
                const oldIndex = columns.indexOf(active.id as ColumnKey);
                const newIndex = columns.indexOf(over.id as ColumnKey);
                setColumns(arrayMove(columns, oldIndex, newIndex));
              }
            }}
          >
            <SortableContext items={columns} strategy={verticalListSortingStrategy}>
              <ul className="space-y-2 max-h-72 overflow-auto pr-2">
                {columns.map((c) => (
                  <li
                    key={c}
                    id={c}
                    className="flex items-center justify-between gap-2 bg-[#202634] rounded-lg px-3 py-2"
                  >
                    <span className="cursor-grab">{COLUMN_LABELS[c]}</span>
                    <label className="flex items-center gap-1 text-sm">
                      <input
                        type="checkbox"
                        checked={!hidden.has(c)}
                        onChange={(e) => {
                          const h = new Set(hidden);
                          if (e.target.checked) h.delete(c);
                          else h.add(c);
                          setHidden(h);
                        }}
                      />
                      Показать
                    </label>
                  </li>
                ))}
              </ul>
            </SortableContext>
          </DndContext>
          <div className="flex justify-end mt-3">
            <button className="btn" onClick={() => setOpen(false)}>
              Ок
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

