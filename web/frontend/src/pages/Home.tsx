import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { Pipeline } from "../components/Pipeline";
import { Reveal, useCountUp } from "../components/Reveal";
import type { Overview } from "../types";

/* Иконки — тонкий контур в акцентном цвете. Эмодзи здесь выбивались:
   каждый в своей манере и своей палитре, мимо стиля страницы. */
const ICONS: Record<string, JSX.Element> = {
  target: (
    <>
      <circle cx="12" cy="12" r="8" />
      <circle cx="12" cy="12" r="3.5" />
      <path d="M12 1.5v3M12 19.5v3M1.5 12h3M19.5 12h3" />
    </>
  ),
  folder: (
    <>
      <path d="M3 7.5A1.5 1.5 0 0 1 4.5 6h4l2 2.5h7A1.5 1.5 0 0 1 19 10v7.5A1.5 1.5 0 0 1 17.5 19h-13A1.5 1.5 0 0 1 3 17.5z" />
      <path d="M3 11h16" />
    </>
  ),
  chart: (
    <>
      <path d="M4 20V4M4 20h16" />
      <path d="M8 20v-6M12.5 20V9M17 20v-9" />
    </>
  ),
  help: (
    <>
      <path d="M4 5.5A1.5 1.5 0 0 1 5.5 4h13A1.5 1.5 0 0 1 20 5.5v9a1.5 1.5 0 0 1-1.5 1.5H9l-5 4z" />
      <path d="M9.8 8.6a2.3 2.3 0 1 1 2.9 2.6v1.3" />
      <path d="M12.7 15.1h.01" />
    </>
  ),
};

/** Склонение существительного по числу: plural(3, ["центр","центра","центров"]) → "центра". */
function plural(n: number, forms: [string, string, string]): string {
  const mod100 = Math.abs(n) % 100;
  const mod10 = mod100 % 10;
  if (mod100 >= 11 && mod100 <= 14) return forms[2];
  if (mod10 === 1) return forms[0];
  if (mod10 >= 2 && mod10 <= 4) return forms[1];
  return forms[2];
}

function Icon({ name }: { name: string }) {
  return (
    <span className="nc-icon" aria-hidden="true">
      <svg viewBox="0 0 24 24" fill="none" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
        {ICONS[name]}
      </svg>
    </span>
  );
}

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
          <h2 className="section-title">Куда дальше</h2>
          <p className="muted">Текущее состояние системы — и переход туда, где нужно ваше участие.</p>
        </div>
        <div className="next-grid">
          <Link className="next-card" to="/exercises">
            <Icon name="target" />
            <h3>Упражнения</h3>
            <div className="nc-stat">
              {ov ? (
                <>
                  <b>{ov.catalog.usable}</b> из {ov.catalog.total}{" "}
                  {plural(ov.catalog.usable, ["готово", "готовы", "готовы"])} к оценке
                  {ov.catalog.needs_notebook > 0 && (
                    <span className="nc-warn">
                      {" "}
                      · {ov.catalog.needs_notebook}{" "}
                      {plural(ov.catalog.needs_notebook, ["ждёт", "ждут", "ждут"])} блокнота
                    </span>
                  )}
                </>
              ) : (
                "каталог упражнений"
              )}
            </div>
            <p className="muted">
              Материалы, блокнот и проверка понимания ИИ. Отсюда упражнения попадают в оценку.
            </p>
            <span className="nc-go">Открыть каталог</span>
          </Link>

          <Link className="next-card" to="/workspace">
            <Icon name="folder" />
            <h3>Центры</h3>
            <div className="nc-stat">
              {ov ? (
                <>
                  <b>{ov.counts.centers}</b> {plural(ov.counts.centers, ["центр", "центра", "центров"])}{" "}
                  · <b>{ov.counts.participants}</b>{" "}
                  {plural(ov.counts.participants, ["участник", "участника", "участников"])}
                </>
              ) : (
                "рабочее пространство"
              )}
            </div>
            <p className="muted">
              Создание центров и участников, загрузка записей, проведение оценки.
            </p>
            <span className="nc-go">Перейти к оценке</span>
          </Link>

          <Link className="next-card" to="/analytics">
            <Icon name="chart" />
            <h3>Аналитика</h3>
            <div className="nc-stat">
              {ov ? (
                <>
                  <b>{ov.counts.processed}</b>{" "}
                  {plural(ov.counts.processed, ["упражнение", "упражнения", "упражнений"])} обработано
                  {ov.measurements > 0 && <> · средний уровень <b>{ov.avg_level}</b></>}
                </>
              ) : (
                "метрики по всем центрам"
              )}
            </div>
            <p className="muted">
              Средние уровни компетенций, распределение оценок и разрез по центрам.
            </p>
            <span className="nc-go">Смотреть метрики</span>
          </Link>

          <Link className="next-card" to="/faq">
            <Icon name="help" />
            <h3>Вопросы и ответы</h3>
            <div className="nc-stat">как всё устроено</div>
            <p className="muted">
              Как считаются уровни, что такое «НЗ», какие форматы файлов, что с приватностью.
            </p>
            <span className="nc-go">Читать ответы</span>
          </Link>
        </div>
      </Reveal>
    </>
  );
}
