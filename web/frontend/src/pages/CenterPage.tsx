import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import type { Center, Participant } from "../types";

export default function CenterPage() {
  const { id } = useParams();
  const centerId = Number(id);
  const [center, setCenter] = useState<Center | null>(null);
  const [parts, setParts] = useState<Participant[]>([]);
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = async () => {
    try {
      setCenter(await api.getCenter(centerId));
      setParts(await api.listParticipants(centerId));
    } catch (e: any) {
      setError(e.message);
    }
  };

  useEffect(() => {
    load();
  }, [centerId]);

  const add = async () => {
    setBusy(true);
    setError("");
    try {
      await api.createParticipant(centerId, code.trim() || undefined);
      setCode("");
      await load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <div className="crumbs">
        <Link to="/">Центры</Link> / {center?.name ?? "…"}
      </div>
      <div className="card">
        <h1>{center?.name ?? "Центр"}</h1>
        <h2 style={{ marginTop: 16 }}>Добавить участника</h2>
        <p className="muted">
          Код/номер участника без ФИО. Оставьте пустым — присвоится автоматически.
        </p>
        <div className="row" style={{ marginTop: 8 }}>
          <input
            type="text"
            placeholder="Код участника (необязательно)"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && add()}
          />
          <button onClick={add} disabled={busy}>
            Добавить
          </button>
        </div>
        {error && <div className="error">{error}</div>}
      </div>

      <div className="card">
        <h2>Участники</h2>
        {parts.length === 0 && <p className="muted">Пока нет участников.</p>}
        <ul className="list">
          {parts.map((p) => (
            <li key={p.id}>
              <Link to={`/participants/${p.id}`}>Участник {p.code}</Link>
              <span className="pill">#{p.id}</span>
            </li>
          ))}
        </ul>
      </div>
    </>
  );
}
