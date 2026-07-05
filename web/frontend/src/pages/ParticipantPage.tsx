import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import type { Exercise, Participant } from "../types";

export default function ParticipantPage() {
  const { id } = useParams();
  const pid = Number(id);
  const [part, setPart] = useState<Participant | null>(null);
  const [exercises, setExercises] = useState<Exercise[]>([]);
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  const load = async () => {
    try {
      setPart(await api.getParticipant(pid));
      setExercises(await api.listExercises(pid));
    } catch (e: any) {
      setError(e.message);
    }
  };

  useEffect(() => {
    load();
  }, [pid]);

  const add = async () => {
    if (!name.trim() || !part) return;
    setBusy(true);
    setError("");
    try {
      await api.createExercise(part.center_id, pid, name.trim());
      setName("");
      await load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const report = async () => {
    setBusy(true);
    setError("");
    setMsg("");
    try {
      await api.buildReport(pid);
      setMsg("Отчёт сформирован — можно скачать DOCX/PPTX и ИПР.");
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const dl = (fn: () => Promise<void>) => fn().catch((e: any) => setError(e.message));

  return (
    <>
      <div className="crumbs">
        {part && <Link to={`/centers/${part.center_id}`}>Центр</Link>} / Участник {part?.code ?? "…"}
      </div>
      <div className="card">
        <h1>Участник {part?.code ?? ""}</h1>
        <div className="row" style={{ marginTop: 12 }}>
          <input
            type="text"
            placeholder="Название упражнения (напр. Беседа с сотрудником)"
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && add()}
          />
          <button onClick={add} disabled={busy}>
            Добавить упражнение
          </button>
        </div>
        {error && <div className="error">{error}</div>}
      </div>

      <div className="card">
        <h2>Упражнения</h2>
        {exercises.length === 0 && <p className="muted">Пока нет упражнений.</p>}
        <ul className="list">
          {exercises.map((e) => (
            <li key={e.id}>
              <Link to={`/exercises/${e.id}`}>{e.name}</Link>
              <span className="pill">#{e.id}</span>
            </li>
          ))}
        </ul>
      </div>

      <div className="card">
        <h2>Отчёт и ИПР</h2>
        <p className="muted">Собирается по всем обработанным упражнениям участника.</p>
        <div className="row" style={{ marginTop: 8 }}>
          <button onClick={report} disabled={busy}>
            Сформировать отчёт
          </button>
          <button className="ghost" onClick={() => dl(() => api.downloadReport(pid, "docx"))}>
            Скачать DOCX
          </button>
          <button className="ghost" onClick={() => dl(() => api.downloadReport(pid, "pptx"))}>
            Скачать PPTX
          </button>
          <button className="ghost" onClick={() => dl(() => api.downloadIpr(pid))}>
            Скачать ИПР
          </button>
        </div>
        {msg && <div className="ok">{msg}</div>}
      </div>
    </>
  );
}
