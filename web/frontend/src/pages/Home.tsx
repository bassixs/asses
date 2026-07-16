import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import type { Overview } from "../types";

const STEPS = [
  {
    n: "01",
    title: "Центр и участники",
    text: "Создаёте центр оценки и добавляете участников по коду или номеру — без ФИО, приватно.",
  },
  {
    n: "02",
    title: "Загрузка материалов",
    text: "К каждому упражнению — аудиозапись беседы и пустой блокнот наблюдателя. Или сразу готовый блокнот, заполненный HR вручную.",
  },
  {
    n: "03",
    title: "Оценка на ИИ",
    text: "Система расшифровывает запись, различает роли (ведущий / участник), оценивает поведенческие индикаторы и выставляет уровни по формуле ТЗ.",
  },
  {
    n: "04",
    title: "Отчёт и ИПР",
    text: "Получаете заполненный блокнот, отчёт участника (DOCX / PPTX) и индивидуальный план развития — готовые к выдаче.",
  },
];

const SECTIONS = [
  { to: "/workspace", icon: "🗂", title: "Центры", text: "Рабочее пространство: центры, участники, упражнения и загрузка файлов." },
  { to: "/analytics", icon: "📈", title: "Аналитика", text: "Метрики по всем центрам: средние уровни компетенций и распределение оценок." },
  { to: "/faq", icon: "💬", title: "Вопросы и ответы", text: "Как считаются уровни, какие форматы файлов, что с приватностью и точностью." },
];

export default function Home() {
  const [ov, setOv] = useState<Overview | null>(null);

  useEffect(() => {
    api.getOverview().then(setOv).catch(() => setOv(null));
  }, []);

  return (
    <>
      <section className="hero">
        <span className="eyebrow">✦ Оценка компетенций на ИИ</span>
        <h1>
          Ассессмент-центр, <span className="accent">собранный сам</span>
        </h1>
        <p>
          Загрузите запись беседы и блокнот наблюдателя — система расшифрует разговор, оценит
          поведенческие индикаторы по формуле ТЗ и соберёт отчёт с индивидуальным планом развития.
          Без ручной разметки и без ФИО.
        </p>
        <div className="hero-cta">
          <Link className="btn" to="/workspace">Перейти в рабочее пространство →</Link>
          <Link className="btn ghost" to="/faq">Как это устроено</Link>
        </div>
        {ov && (
          <div className="hero-stats">
            <div><b>{ov.counts.centers}</b> центров</div>
            <div><b>{ov.counts.participants}</b> участников</div>
            <div><b>{ov.counts.processed}</b> упражнений обработано</div>
          </div>
        )}
      </section>

      <section className="section">
        <div className="section-head">
          <h2 className="section-title">Как это работает</h2>
          <p className="muted">Четыре шага от записи к готовому отчёту.</p>
        </div>
        <div className="steps-grid">
          {STEPS.map((s) => (
            <div className="step-card" key={s.n}>
              <span className="step-num">{s.n}</span>
              <h3>{s.title}</h3>
              <p className="muted">{s.text}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="section">
        <div className="section-head">
          <h2 className="section-title">Разделы</h2>
        </div>
        <div className="cards-grid">
          {SECTIONS.map((s) => (
            <Link className="nav-card" to={s.to} key={s.to}>
              <span className="nav-card-icon">{s.icon}</span>
              <h3>{s.title}</h3>
              <p className="muted">{s.text}</p>
              <span className="nav-card-go">Открыть →</span>
            </Link>
          ))}
        </div>
      </section>
    </>
  );
}
