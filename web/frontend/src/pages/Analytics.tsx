import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { ConfirmDelete } from "../components/ConfirmDelete";
import { CountUp } from "../components/Reveal";
import type { Overview, Storage } from "../types";
import { BandBar, BarList, Gauge, StatTile } from "../components/Charts";

const mb = (bytes: number) => `${(bytes / 1024 / 1024).toFixed(1)} МБ`;

function StorageCard() {
  const [st, setSt] = useState<Storage | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");
  const [showList, setShowList] = useState(false);

  const load = () => api.getStorage().then(setSt).catch((e: any) => setError(e.message));

  useEffect(() => {
    load();
  }, []);

  const cleanup = async () => {
    setBusy(true);
    setError("");
    setMsg("");
    try {
      const r = await api.cleanupStorage();
      setMsg(`Удалено файлов: ${r.deleted}, освобождено ${mb(r.freed)}.`);
      setShowList(false);
      await load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  if (!st) return null;

  return (
    <div className="card">
      <h2>Хранилище файлов</h2>
      <p className="muted">
        Записи, блокноты и отчёты лежат файлами на сервере. Когда вы удаляете центр или
        участника, записи в базе пропадают, а файлы остаются — их не видно с сайта, но они
        занимают место. Здесь их можно убрать.
      </p>

      <div className="catalog-row">
        <div className="catalog-item">
          <b>{st.total_files}</b>
          <span>файлов всего · {mb(st.total_size)}</span>
        </div>
        <div className={`catalog-item ${st.orphan_count > 0 ? "warn" : "ok"}`}>
          <b>{st.orphan_count}</b>
          <span>ничейных · {mb(st.orphan_size)}</span>
        </div>
        {st.orphan_count > 0 && (
          <button className="ghost" onClick={() => setShowList(!showList)}>
            {showList ? "Скрыть список" : "Показать список"}
          </button>
        )}
      </div>

      {showList && (
        <ul className="file-list" style={{ marginTop: 16 }}>
          {st.orphans.map((f) => (
            <li key={f.name}>
              <span>📄 {f.name}</span>
              <span className="muted">
                {mb(f.size)} · {Math.round(f.age_hours)} ч назад
              </span>
            </li>
          ))}
        </ul>
      )}

      {st.orphan_count > 0 ? (
        <div style={{ marginTop: 16 }}>
          <ConfirmDelete
            busy={busy}
            what={`${st.orphan_count} ничейных файлов (${mb(st.orphan_size)})`}
            onConfirm={cleanup}
          />
          <p className="muted" style={{ marginTop: 10 }}>
            Удаляются только файлы, на которые ничто не ссылается. Файлы моложе{" "}
            {st.min_age_minutes} минут не трогаются — они могут быть в обработке прямо сейчас
            {st.skipped_recent > 0 ? ` (сейчас таких: ${st.skipped_recent})` : ""}.
          </p>
        </div>
      ) : (
        <p className="ok" style={{ marginTop: 12 }}>
          Ничейных файлов нет — всё, что лежит на диске, используется.
        </p>
      )}

      {msg && <div className="ok">{msg}</div>}
      {error && <div className="error">{error}</div>}
    </div>
  );
}

export default function Analytics() {
  const [ov, setOv] = useState<Overview | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.getOverview().then(setOv).catch((e: any) => setError(e.message));
  }, []);

  if (error) return <div className="card"><div className="error">{error}</div></div>;
  if (!ov) return <div className="card"><p className="muted">Загрузка метрик…</p></div>;

  const c = ov.counts;
  const empty = ov.measurements === 0;

  return (
    <>
      <div className="page-head">
        <h1>Аналитика</h1>
        <p className="muted">
          Сводка по всем центрам оценки. Уровни компетенций — по шкале ТЗ от 0 до {ov.level_max}.
        </p>
      </div>

      <div className="stat-grid">
        <StatTile label="Центров оценки" value={<CountUp value={c.centers} />} />
        <StatTile label="Участников" value={<CountUp value={c.participants} />} />
        <StatTile
          label="Упражнений обработано"
          value={<CountUp value={c.processed} />}
          hint={`всего создано: ${c.exercises}`}
        />
        <StatTile label="Отчётов собрано" value={<CountUp value={c.reports} />} />
      </div>

      <div className="card">
        <h2>Готовность каталога упражнений</h2>
        <p className="muted">
          Выбрать при оценке можно только упражнения, которые ИИ разобрал, HR активировал и у
          которых приложен блокнот.
        </p>
        <div className="catalog-row">
          <div className="catalog-item ok">
            <b>{ov.catalog.usable}</b>
            <span>готовы к оценке</span>
          </div>
          <div className="catalog-item warn">
            <b>{ov.catalog.needs_notebook}</b>
            <span>ждут блокнота</span>
          </div>
          <div className="catalog-item draft">
            <b>{ov.catalog.draft}</b>
            <span>черновики</span>
          </div>
          <Link className="catalog-link" to="/exercises">
            Открыть каталог →
          </Link>
        </div>
      </div>

      {empty ? (
        <div className="card">
          <h2>Пока нет обработанных упражнений</h2>
          <p className="muted">
            Как только вы обработаете первое упражнение, здесь появятся средние уровни компетенций и
            распределение оценок. <Link to="/workspace">Перейти в рабочее пространство →</Link>
          </p>
        </div>
      ) : (
        <>
          <div className="grid-2">
            <div className="card">
              <h2>Средний уровень</h2>
              <p className="muted">По всем {ov.measurements} измерениям компетенций.</p>
              <Gauge value={ov.avg_level} max={ov.level_max} caption="средний уровень компетенций" />
            </div>

            <div className="card">
              <h2>Распределение оценок</h2>
              <p className="muted">Как измерения компетенций разложились по уровням ТЗ.</p>
              <BandBar data={ov.level_bands} />
            </div>
          </div>

          <div className="card">
            <h2>Средний уровень по компетенциям</h2>
            <p className="muted">Отсортировано по убыванию. Наведите на строку — покажет число измерений.</p>
            <BarList
              data={ov.avg_by_competence.map((x) => ({ name: x.name, value: x.avg, count: x.count }))}
              max={ov.level_max}
            />
          </div>

          {ov.by_center.length > 0 && (
            <div className="card">
              <h2>По центрам оценки</h2>
              <p className="muted">Прогресс обработки и средний уровень в каждом центре.</p>
              <div className="center-rows">
                {ov.by_center.map((b) => {
                  const pct = b.exercises > 0 ? Math.round((b.processed / b.exercises) * 100) : 0;
                  return (
                    <Link className="center-row" to={`/centers/${b.id}`} key={b.id}>
                      <div className="cr-top">
                        <span className="cr-name">{b.name}</span>
                        <span className="cr-level">
                          {b.avg_level != null ? b.avg_level.toFixed(1) : "—"}
                          <small>ур.</small>
                        </span>
                      </div>
                      <div className="cr-meta muted">
                        {b.participants} участников · {b.processed} из {b.exercises} упражнений обработано
                      </div>
                      <div className="cc-progress">
                        <div className="cc-bar" style={{ width: `${pct}%` }} />
                      </div>
                    </Link>
                  );
                })}
              </div>
            </div>
          )}
        </>
      )}

      <StorageCard />
    </>
  );
}
