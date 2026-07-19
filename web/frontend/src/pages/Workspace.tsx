import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import type { Center } from "../types";

export default function Workspace() {
  const [centers, setCenters] = useState<Center[]>([]);
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = () =>
    api
      .listCenters()
      .then(setCenters)
      .catch((e: any) => setError(e.message));

  useEffect(() => {
    load();
  }, []);

  const create = async () => {
    if (!name.trim()) return;
    setBusy(true);
    setError("");
    try {
      await api.createCenter(name.trim());
      setName("");
      await load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <div className="page-head">
        <h1>Центры оценки</h1>
        <p className="muted">
          Центр — это один поток оценки (например, «Резерв руководителей, июль»). Внутри центра —
          участники, у каждого участника — упражнения.
        </p>
      </div>

      <div className="card">
        <h2>Новый центр</h2>
        <div className="row">
          <input
            type="text"
            placeholder="Название центра"
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && create()}
          />
          <button onClick={create} disabled={busy}>
            Создать
          </button>
        </div>
        {error && <div className="error">{error}</div>}
      </div>

      {centers.length === 0 ? (
        <div className="card">
          <h2>Список центров</h2>
          <p className="muted">Пока нет центров. Создайте первый — с него начинается работа.</p>
        </div>
      ) : (
        <>
          <h2 className="section-title" style={{ margin: "26px 0 14px" }}>
            Список центров
          </h2>
          <div className="center-grid">
            {centers.map((c) => {
              const total = c.exercises ?? 0;
              const done = c.processed ?? 0;
              const pct = total > 0 ? Math.round((done / total) * 100) : 0;
              return (
                <Link className="center-card" to={`/centers/${c.id}`} key={c.id}>
                  <div className="cc-head">
                    <h3>{c.name}</h3>
                    <span className="pill">#{c.id}</span>
                  </div>
                  {c.created_at && (
                    <div className="cc-date">
                      создан {new Date(c.created_at).toLocaleDateString("ru-RU")}
                    </div>
                  )}
                  <div className="cc-stats">
                    <div>
                      <b>{c.participants ?? 0}</b>
                      <span>участников</span>
                    </div>
                    <div>
                      <b>{total}</b>
                      <span>упражнений</span>
                    </div>
                    <div>
                      <b>{done}</b>
                      <span>обработано</span>
                    </div>
                  </div>
                  <div className="cc-progress" title={`Обработано ${done} из ${total}`}>
                    <div className="cc-bar" style={{ width: `${pct}%` }} />
                  </div>
                  <div className="cc-foot">
                    {total === 0
                      ? "упражнений ещё нет"
                      : done === total
                        ? "✓ все упражнения обработаны"
                        : `обработано ${pct}%`}
                    <span className="cc-go">Открыть →</span>
                  </div>
                </Link>
              );
            })}
          </div>
        </>
      )}
    </>
  );
}
