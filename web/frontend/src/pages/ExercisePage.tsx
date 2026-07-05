import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import type { Exercise, ExerciseStatus } from "../types";

type Method = "" | "audio" | "filled";

export default function ExercisePage() {
  const { id } = useParams();
  const exId = Number(id);
  const [ex, setEx] = useState<Exercise | null>(null);
  const [method, setMethod] = useState<Method>("");
  const [instrMsg, setInstrMsg] = useState("");
  const [notebookMsg, setNotebookMsg] = useState("");
  const [status, setStatus] = useState<ExerciseStatus | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const pollRef = useRef<number | null>(null);

  const loadStatus = async () => {
    try {
      setStatus(await api.exerciseStatus(exId));
    } catch {
      /* ignore */
    }
  };

  useEffect(() => {
    api.getExercise(exId).then(setEx).catch((e: any) => setError(e.message));
    loadStatus();
    return () => {
      if (pollRef.current) window.clearInterval(pollRef.current);
    };
  }, [exId]);

  const wrap = async (fn: () => Promise<void>) => {
    setBusy(true);
    setError("");
    try {
      await fn();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const onInstr = (f?: File | null) =>
    f &&
    wrap(async () => {
      const r = await api.uploadInstructions(exId, f);
      setInstrMsg(`Инструкция добавлена (${r.chars} символов).`);
      setEx(await api.getExercise(exId));
    });

  const onTemplate = (f?: File | null) =>
    f &&
    wrap(async () => {
      const r = await api.uploadNotebookTemplate(exId, f);
      setNotebookMsg(`Блокнот-шаблон принят (${r.indicators} индикаторов).`);
    });

  const startPoll = () => {
    if (pollRef.current) window.clearInterval(pollRef.current);
    pollRef.current = window.setInterval(async () => {
      const s = await api.exerciseStatus(exId);
      setStatus(s);
      if (s.stage === "done" || s.stage === "error") {
        if (pollRef.current) window.clearInterval(pollRef.current);
      }
    }, 3000);
  };

  const onAudio = (f?: File | null) =>
    f &&
    wrap(async () => {
      await api.uploadAudio(exId, f);
      setStatus({ stage: "processing", message: "Расшифровка и анализ…", has_result: false, levels: {}, indicator_count: null });
      startPoll();
    });

  const onFilled = (f?: File | null) =>
    f &&
    wrap(async () => {
      await api.uploadFilledNotebook(exId, f);
      await loadStatus();
    });

  const levels = status?.levels ?? {};
  const done = status?.has_result;
  const stageText =
    status?.stage === "processing"
      ? "⏳ обработка…"
      : status?.stage === "error"
        ? "⚠️ ошибка"
        : status?.stage === "done"
          ? "✅ готово"
          : status?.stage ?? "";

  return (
    <>
      <div className="crumbs">
        {ex && <Link to={`/participants/${ex.participant_id}`}>Участник</Link>} / {ex?.name ?? "…"}
      </div>
      <div className="card">
        <h1>{ex?.name ?? "Упражнение"}</h1>

        <div className="step">
          <h2>1. Инструкции упражнения (по желанию)</h2>
          <p className="muted">
            PDF или DOCX. Помогают точнее определить роли и «НЗ».{" "}
            {ex?.has_instructions && <span className="pill">✓ загружены</span>}
          </p>
          <input type="file" accept=".pdf,.docx" disabled={busy} onChange={(e) => onInstr(e.target.files?.[0])} />
          {instrMsg && <div className="ok">{instrMsg}</div>}
        </div>

        <div className={`step ${method ? "active" : ""}`}>
          <h2>2. Способ оценки</h2>
          <div className="row">
            <button className={method === "audio" ? "" : "ghost"} onClick={() => setMethod("audio")}>
              🎙 По аудиозаписи
            </button>
            <button className={method === "filled" ? "" : "ghost"} onClick={() => setMethod("filled")}>
              📊 Загрузить заполненный блокнот
            </button>
          </div>
        </div>

        {method === "audio" && (
          <div className="step active">
            <h2>3. Аудио + блокнот</h2>
            <p className="muted">
              Сначала загрузите пустой блокнот наблюдателя (.xlsx), затем аудио — система расшифрует и заполнит блокнот.
            </p>
            <div style={{ marginBottom: 10 }}>
              <b>Блокнот-шаблон (.xlsx):</b>{" "}
              <input type="file" accept=".xlsx" disabled={busy} onChange={(e) => onTemplate(e.target.files?.[0])} />
              {notebookMsg && <div className="ok">{notebookMsg}</div>}
            </div>
            <div>
              <b>Аудио:</b>{" "}
              <input type="file" accept="audio/*,.mp3,.ogg,.m4a,.wav" disabled={busy} onChange={(e) => onAudio(e.target.files?.[0])} />
            </div>
          </div>
        )}

        {method === "filled" && (
          <div className="step active">
            <h2>3. Заполненный блокнот</h2>
            <p className="muted">Наблюдатель уже проставил статусы и уровни — система прочитает их как есть.</p>
            <input type="file" accept=".xlsx" disabled={busy} onChange={(e) => onFilled(e.target.files?.[0])} />
          </div>
        )}

        {error && <div className="error">{error}</div>}
      </div>

      {status && status.stage !== "idle" && (
        <div className="card">
          <h2>Результат</h2>
          <p className="muted">
            Статус: {stageText}
            {status.message ? ` — ${status.message}` : ""}
          </p>
          {done && (
            <>
              {Object.keys(levels).length > 0 && (
                <table className="levels">
                  <tbody>
                    {Object.entries(levels).map(([name, l]) => (
                      <tr key={name}>
                        <td>{name}</td>
                        <td className="lvl">{l.level}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              <div className="row" style={{ marginTop: 12 }}>
                <button className="ghost" onClick={() => api.downloadFilledNotebook(exId).catch((e: any) => setError(e.message))}>
                  Скачать заполненный блокнот
                </button>
              </div>
            </>
          )}
        </div>
      )}
    </>
  );
}
