import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import type { Center } from "../types";

export default function Dashboard() {
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
      <div className="hero">
        <span className="eyebrow">✦ Оценка компетенций на ИИ</span>
        <h1>
          Центры оценки — <span className="accent">быстро и наглядно</span>
        </h1>
        <p>
          Создавайте центры и участников, загружайте аудио или готовый блокнот — система
          расшифрует, оценит по индикаторам и соберёт отчёт с ИПР.
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
        {centers.length === 0 && <p className="muted">Пока нет центров.</p>}
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
