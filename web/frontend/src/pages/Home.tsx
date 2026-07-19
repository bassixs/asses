import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { Pipeline } from "../components/Pipeline";
import { Reveal, useCountUp } from "../components/Reveal";
import type { Overview } from "../types";

const SECTIONS = [
  { to: "/exercises", icon: "🎯", title: "Упражнения", text: "Каталог: материалы, блокнот и проверка понимания ИИ. Отсюда упражнения попадают в оценку." },
  { to: "/workspace", icon: "🗂", title: "Центры", text: "Рабочее пространство: центры, участники и проведение оценки." },
  { to: "/analytics", icon: "📈", title: "Аналитика", text: "Метрики по всем центрам: средние уровни компетенций и распределение оценок." },
  { to: "/faq", icon: "💬", title: "Вопросы и ответы", text: "Как считаются уровни, какие форматы файлов, что с приватностью и точностью." },
];

const CLAIMS = [
  {
    big: "5 минут",
    label: "от записи до заполненного блокнота",
    note: "Проверено на реальном файле: 59 МБ, 45 минут беседы.",
  },
  {
    big: "89",
    label: "индикаторов за один прогон",
    note: "Столько строк наблюдатель размечает вручную по одному участнику.",
  },
  {
    big: "0",
    label: "выдуманных цитат",
    note: "Каждое подтверждение сверяется с расшифровкой дословно, иначе отбраковывается.",
  },
];

const BEFORE = [
  "Наблюдатель размечает 89 индикаторов вручную",
  "Разные эксперты — разные трактовки одного поведения",
  "Часы на расшифровку и сбор отчёта",
  "Обоснования по памяти, без ссылки на запись",
];

const AFTER = [
  "Черновая разметка готова за минуты",
  "Одна формула ТЗ для всех участников",
  "Отчёт и ИПР собираются сами",
  "У каждого «+» — дословная цитата с таймкодом",
];

function LiveStat({ value, label }: { value: number; label: string }) {
  const shown = useCountUp(value);
  return (
    <div className="live-stat">
      <b>{shown}</b>
      <span>{label}</span>
    </div>
  );
}

export default function Home() {
  const [ov, setOv] = useState<Overview | null>(null);

  useEffect(() => {
    api.getOverview().then(setOv).catch(() => setOv(null));
  }, []);

  return (
    <>
      <section className="hero hero-xl">
        <div className="aurora" aria-hidden="true">
          <span className="a1" />
          <span className="a2" />
          <span className="a3" />
        </div>

        <span className="eyebrow">✦ Оценка компетенций на ИИ</span>
        <h1>
          Ассессмент-центр,
          <br />
          который <span className="accent">собирает себя сам</span>
        </h1>
        <p>
          Загрузите запись упражнения — система расшифрует разговор, отличит ведущего от участника,
          оценит поведенческие индикаторы по формуле ТЗ и соберёт отчёт с планом развития.
          Каждый вывод подкреплён цитатой из записи.
        </p>
        <div className="hero-cta">
          <Link className="btn" to="/workspace">
            Перейти к оценке →
          </Link>
          <Link className="btn ghost" to="/exercises">
            Каталог упражнений
          </Link>
        </div>

        {ov && (
          <div className="live-strip">
            <LiveStat value={ov.counts.centers} label="центров оценки" />
            <LiveStat value={ov.counts.participants} label="участников" />
            <LiveStat value={ov.counts.processed} label="упражнений обработано" />
            <LiveStat value={ov.counts.reports} label="отчётов собрано" />
          </div>
        )}
      </section>

      <Reveal className="section">
        <div className="section-head center">
          <h2 className="section-title">Как это работает</h2>
          <p className="muted">
            Один и тот же путь для каждого участника — от записи до уровня компетенции.
          </p>
        </div>
        <Pipeline />
      </Reveal>

      <Reveal className="section">
        <div className="claims">
          {CLAIMS.map((c, i) => (
            <div className="claim" key={i}>
              <b>{c.big}</b>
              <span className="claim-label">{c.label}</span>
              <span className="claim-note">{c.note}</span>
            </div>
          ))}
        </div>
      </Reveal>

      <Reveal className="section">
        <div className="section-head center">
          <h2 className="section-title">Что меняется</h2>
        </div>
        <div className="ba">
          <div className="ba-col before">
            <h3>Вручную</h3>
            <ul>
              {BEFORE.map((t, i) => (
                <li key={i}>{t}</li>
              ))}
            </ul>
          </div>
          <div className="ba-col after">
            <h3>С системой</h3>
            <ul>
              {AFTER.map((t, i) => (
                <li key={i}>{t}</li>
              ))}
            </ul>
          </div>
        </div>
        <p className="ba-foot muted">
          Решение остаётся за наблюдателем: система готовит черновик и расчёт, а заполненный
          блокнот и отчёт можно проверить и поправить.
        </p>
      </Reveal>

      <Reveal className="section">
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
      </Reveal>
    </>
  );
}
