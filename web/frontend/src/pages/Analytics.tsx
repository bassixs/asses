import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import type { Overview } from "../types";
import { BandBar, BarList, Gauge, StatTile } from "../components/Charts";

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
        <StatTile label="Центров оценки" value={c.centers} />
        <StatTile label="Участников" value={c.participants} />
        <StatTile label="Упражнений обработано" value={c.processed} hint={`всего создано: ${c.exercises}`} />
        <StatTile label="Отчётов собрано" value={c.reports} />
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
        </>
      )}
    </>
  );
}
