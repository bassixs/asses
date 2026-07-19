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
        <p className="muted">
          Материалы и блокнот наблюдателя взяты из каталога упражнения
          {ex?.notebook_indicator_count ? ` (${ex.notebook_indicator_count} индикаторов)` : ""}.
          {ex?.template_id && (
            <>
              {" "}
              <Link to={`/exercises/${ex.template_id}`}>Открыть карточку упражнения →</Link>
            </>
          )}
        </p>

        <div className={`step ${method ? "active" : ""}`}>
          <h2>1. Способ оценки</h2>
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
            <h2>2. Аудиозапись</h2>
            <p className="muted">
              Блокнот наблюдателя уже взят из каталога — загрузите только запись. Система расшифрует
              её, разметит роли и заполнит блокнот.
            </p>
            <input
              type="file"
              accept="audio/*,.mp3,.ogg,.m4a,.wav"
              disabled={busy}
              onChange={(e) => onAudio(e.target.files?.[0])}
            />
          </div>
        )}

        {method === "filled" && (
          <div className="step active">
            <h2>2. Заполненный блокнот</h2>
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
