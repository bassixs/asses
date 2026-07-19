import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import type { ExerciseTemplate } from "../types";
import { StatusBadge } from "./ExerciseLibrary";

function List({ title, items }: { title: string; items: string[] }) {
  if (!items || items.length === 0) return null;
  return (
    <div className="u-block">
      <h4>{title}</h4>
      <ul className="u-list">
        {items.map((x, i) => (
          <li key={i}>{x}</li>
        ))}
      </ul>
    </div>
  );
}

function Field({ title, value }: { title: string; value?: string }) {
  if (!value) return null;
  return (
    <div className="u-block">
      <h4>{title}</h4>
      <p className="muted">{value}</p>
    </div>
  );
}

export default function TemplatePage() {
  const { id } = useParams();
  const tid = Number(id);
  const [t, setT] = useState<ExerciseTemplate | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [checking, setChecking] = useState(false);

  useEffect(() => {
    api.getTemplate(tid).then(setT).catch((e: any) => setError(e.message));
  }, [tid]);

  const wrap = async (fn: () => Promise<ExerciseTemplate>) => {
    setBusy(true);
    setError("");
    try {
      setT(await fn());
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const runCheck = async () => {
    setChecking(true);
    setError("");
    try {
      setT(await api.checkTemplate(tid));
    } catch (e: any) {
      setError(e.message);
    } finally {
      setChecking(false);
    }
  };

  if (error && !t) return <div className="card"><div className="error">{error}</div></div>;
  if (!t) return <div className="card"><p className="muted">Загрузка…</p></div>;

  const u = t.understanding;
  const canCheck = t.has_notebook && t.instructions_chars > 0;

  return (
    <>
      <div className="crumbs">
        <Link to="/exercises">Упражнения</Link> / {t.name}
      </div>

      <div className="card">
        <div className="head-row">
          <h1>{t.name}</h1>
          <StatusBadge t={t} />
        </div>
        {t.description && <p className="muted">{t.description}</p>}
        {t.is_usable && (
          <div className="ok" style={{ marginTop: 10 }}>
            Упражнение доступно для выбора при оценке участников.
          </div>
        )}
      </div>

      <div className="card">
        <div className="step">
          <h2>1. Материалы упражнения</h2>
          <p className="muted">
            Инструкции ведущего, наблюдателя, участника, методички. PDF, DOCX, TXT или MD.
            Можно приложить несколько файлов.
          </p>
          {t.materials && t.materials.length > 0 && (
            <ul className="file-list">
              {t.materials.map((m) => (
                <li key={m.id}>
                  <span>📄 {m.file_name}</span>
                  <span className="muted">{m.chars} символов</span>
                </li>
              ))}
            </ul>
          )}
          <input
            type="file"
            accept=".pdf,.docx,.txt,.md"
            disabled={busy}
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) wrap(() => api.uploadTemplateMaterial(tid, f));
            }}
          />
        </div>

        <div className="step">
          <h2>2. Пустой блокнот наблюдателя</h2>
          <p className="muted">
            Файл .xlsx с компетенциями и индикаторами. Он будет использоваться для всех участников,
            которых оценивают по этому упражнению.{" "}
            {t.has_notebook && (
              <span className="pill good">
                ✓ {t.notebook_file_name} · {t.notebook_indicator_count} индикаторов
              </span>
            )}
          </p>
          <input
            type="file"
            accept=".xlsx"
            disabled={busy}
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) wrap(() => api.uploadTemplateNotebook(tid, f));
            }}
          />
        </div>

        <div className={`step ${canCheck ? "active" : ""}`}>
          <h2>3. Проверка понимания ИИ</h2>
          <p className="muted">
            ИИ изучит материалы и блокнот и разберёт: кто в записи ведущий, кто оцениваемый
            участник, какие ситуации упражнение создаёт и что нельзя замерить. Если материалов не
            хватит — честно скажет, чего именно.
          </p>
          <button onClick={runCheck} disabled={!canCheck || checking || busy}>
            {checking ? "ИИ изучает материалы…" : "Проверить понимание"}
          </button>
          {!canCheck && (
            <p className="muted" style={{ marginTop: 8 }}>
              Нужны и материалы, и блокнот — без них проверять нечего.
            </p>
          )}
        </div>

        {error && <div className="error">{error}</div>}
      </div>

      {u && (
        <div className={`card understanding ${u.understood ? "good" : "bad"}`}>
          <div className="head-row">
            <h2>Что понял ИИ</h2>
            <span className={`badge ${u.understood ? "ok" : "err"}`}>
              {u.understood ? "✓ Понимание подтверждено" : "✗ Понимания не хватает"}
            </span>
          </div>

          {u.understood_reason && <p className="verdict">{u.understood_reason}</p>}

          {u.gaps.length > 0 && (
            <div className="u-block gaps">
              <h4>Чего не хватает</h4>
              <ul className="u-list">
                {u.gaps.map((g, i) => (
                  <li key={i}>{g}</li>
                ))}
              </ul>
              <p className="muted">
                Приложите недостающие материалы и запустите проверку заново.
              </p>
            </div>
          )}

          <Field title="Суть упражнения" value={u.summary} />
          <Field title="Формат" value={u.format} />
          <Field title="Роль оцениваемого участника" value={u.participant_role} />
          <Field title="Роль ведущего / ролевого игрока" value={u.facilitator_role} />
          <List title="Ситуации, которые создаёт упражнение" items={u.expected_situations} />
          <List title="Замеряемые компетенции" items={u.competencies_covered} />
          <List title="Что здесь замерить нельзя (пойдёт в «НЗ»)" items={u.not_observable} />
          <Field title="Как решать про «НЗ»" value={u.nz_guidance} />
        </div>
      )}

      <div className="card">
        <h2>4. Активация</h2>
        {t.is_usable ? (
          <>
            <p className="muted">
              Упражнение опубликовано в каталоге и доступно при оценке участников.
            </p>
            <button className="ghost" disabled={busy} onClick={() => wrap(() => api.deactivateTemplate(tid))}>
              Снять с публикации
            </button>
          </>
        ) : (
          <>
            <p className="muted">
              {!t.understood
                ? "Активировать можно только после того, как ИИ подтвердит полное понимание упражнения."
                : !t.has_notebook
                  ? "ИИ подтвердил понимание, но для использования нужен пустой блокнот наблюдателя."
                  : "ИИ подтвердил понимание — проверьте карточку выше и активируйте упражнение."}
            </p>
            <button
              disabled={busy || !t.understood}
              onClick={() => wrap(() => api.activateTemplate(tid))}
            >
              Активировать упражнение
            </button>
          </>
        )}
      </div>
    </>
  );
}
