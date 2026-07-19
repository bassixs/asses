import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import { ConfirmDelete } from "../components/ConfirmDelete";
import type { Exercise, ExerciseTemplate, Participant } from "../types";

export default function ParticipantPage() {
  const { id } = useParams();
  const pid = Number(id);
  const [part, setPart] = useState<Participant | null>(null);
  const [exercises, setExercises] = useState<Exercise[]>([]);
  const [templates, setTemplates] = useState<ExerciseTemplate[]>([]);
  const [templateId, setTemplateId] = useState("");
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
    api.listTemplates(true).then(setTemplates).catch(() => setTemplates([]));
  }, [pid]);

  const add = async () => {
    if (!templateId || !part) return;
    setBusy(true);
    setError("");
    try {
      await api.createExercise(part.center_id, pid, Number(templateId));
      setTemplateId("");
      await load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const removeExercise = async (exerciseId: number) => {
    setBusy(true);
    setError("");
    try {
      await api.deleteExercise(exerciseId);
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
        <h2 style={{ marginTop: 16 }}>Добавить упражнение</h2>
        <p className="muted">
          Выбирается из <Link to="/exercises">каталога упражнений</Link> — материалы и блокнот
          подтянутся автоматически.
        </p>
        <div className="row" style={{ marginTop: 10 }}>
          <select value={templateId} onChange={(e) => setTemplateId(e.target.value)}>
            <option value="">— выберите упражнение —</option>
            {templates.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>
          <button onClick={add} disabled={busy || !templateId}>
            Добавить
          </button>
        </div>
        {templates.length === 0 && (
          <p className="muted" style={{ marginTop: 10 }}>
            В каталоге пока нет готовых упражнений.{" "}
            <Link to="/exercises">Создать упражнение →</Link>
          </p>
        )}
        {error && <div className="error">{error}</div>}
      </div>

      <div className="card">
        <h2>Упражнения участника</h2>
        {exercises.length === 0 && <p className="muted">Пока нет упражнений.</p>}
        <ul className="list rows">
          {exercises.map((e) => (
            <li key={e.id}>
              <Link className="row-link" to={`/assessments/${e.id}`}>
                <span>{e.name}</span>
                <span className="row-actions">
                  <ConfirmDelete
                    busy={busy}
                    what={`упражнение «${e.name}» и его результат`}
                    onConfirm={() => removeExercise(e.id)}
                  />
                  <span className="pill">#{e.id}</span>
                </span>
              </Link>
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
