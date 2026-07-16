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

      <div className="card">
        <h2>Список центров</h2>
        {centers.length === 0 && (
          <p className="muted">Пока нет центров. Создайте первый — с него начинается работа.</p>
        )}
        <ul className="list">
          {centers.map((c) => (
            <li key={c.id}>
              <Link to={`/centers/${c.id}`}>{c.name}</Link>
              <span className="pill">#{c.id}</span>
            </li>
          ))}
        </ul>
      </div>
    </>
  );
}
