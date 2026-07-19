import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import { ConfirmDelete } from "../components/ConfirmDelete";
import type { Center, Participant } from "../types";

export default function CenterPage() {
  const { id } = useParams();
  const centerId = Number(id);
  const navigate = useNavigate();
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

  const removeParticipant = async (participantId: number) => {
    setBusy(true);
    setError("");
    try {
      await api.deleteParticipant(participantId);
      await load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const removeCenter = async () => {
    setBusy(true);
    setError("");
    try {
      await api.deleteCenter(centerId);
      navigate("/workspace");
    } catch (e: any) {
      setError(e.message);
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
        <ul className="list rows">
          {parts.map((p) => (
            <li key={p.id}>
              <Link className="row-link" to={`/participants/${p.id}`}>
                <span className="li-main">
                  Участник {p.code}
                  <span className="li-sub muted">
                    {p.processed_count
                      ? `оценено упражнений: ${p.processed_count}`
                      : "упражнения ещё не оценены"}
                  </span>
                </span>
                <span className="row-actions">
                  {p.has_report ? (
                    <span className="badge ok">✓ отчёт собран</span>
                  ) : p.processed_count ? (
                    <span className="badge warn">ждёт отчёта</span>
                  ) : null}
                  <ConfirmDelete
                    busy={busy}
                    what={`участника ${p.code} со всеми его упражнениями и отчётами`}
                    onConfirm={() => removeParticipant(p.id)}
                  />
                  <span className="pill">#{p.id}</span>
                </span>
              </Link>
            </li>
          ))}
        </ul>
      </div>

      <div className="card danger-zone">
        <h2>Удаление центра</h2>
        <p className="muted">
          Удалится сам центр, все его участники, упражнения, расшифровки и собранные отчёты.
          Действие необратимо.
        </p>
        <ConfirmDelete
          busy={busy}
          what={`центр «${center?.name ?? ""}» целиком`}
          onConfirm={removeCenter}
        />
      </div>
    </>
  );
}
