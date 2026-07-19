/**
 * Looping visualisation of the whole product in four stages:
 * audio → roles in the transcript → indicators scored → competency level.
 *
 * Pure CSS/SVG, no libraries. The loop is 12s; each stage lights up in turn via
 * animation-delay, so a viewer grasps the pipeline without reading anything.
 */

const WAVE = [10, 22, 38, 26, 46, 62, 40, 28, 54, 70, 44, 30, 18, 34, 50, 24, 12, 40, 58, 32];

const LINES = [
  { role: "Ведущий", text: "Нужно подготовить материалы к пятнице.", who: "host" },
  { role: "Участник", text: "Давайте разобьём на этапы и сверимся в среду.", who: "part" },
  { role: "Ведущий", text: "У меня сейчас нет на это времени.", who: "host" },
  { role: "Участник", text: "Тогда возьму подготовку на себя, вы — согласование.", who: "part" },
];

const INDICATORS = [
  { text: "Структурирует задачу на этапы", status: "+" },
  { text: "Проверяет понимание собеседника", status: "+" },
  { text: "Фиксирует контрольные точки", status: "+" },
  { text: "Работает с возражением", status: "−" },
  { text: "Выступает перед группой", status: "НЗ" },
];

export function Pipeline() {
  return (
    <div className="pipeline">
      <div className="pl-stage">
        <div className="pl-cap">
          <span className="pl-num">01</span> Аудиозапись
        </div>
        <div className="pl-box pl-wave">
          {WAVE.map((h, i) => (
            <span key={i} style={{ height: `${h}%`, animationDelay: `${i * 60}ms` }} />
          ))}
        </div>
      </div>

      <div className="pl-arrow" aria-hidden="true">
        →
      </div>

      <div className="pl-stage">
        <div className="pl-cap">
          <span className="pl-num">02</span> Роли в расшифровке
        </div>
        <div className="pl-box pl-lines">
          {LINES.map((l, i) => (
            <div className="pl-line" key={i} style={{ animationDelay: `${1200 + i * 450}ms` }}>
              <span className={`pl-role ${l.who}`}>{l.role}</span>
              <span className="pl-text">{l.text}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="pl-arrow" aria-hidden="true">
        →
      </div>

      <div className="pl-stage">
        <div className="pl-cap">
          <span className="pl-num">03</span> Индикаторы
        </div>
        <div className="pl-box pl-inds">
          {INDICATORS.map((ind, i) => (
            <div className="pl-ind" key={i} style={{ animationDelay: `${4200 + i * 380}ms` }}>
              <span className="pl-ind-text">{ind.text}</span>
              <span
                className={`pl-badge ${
                  ind.status === "+" ? "yes" : ind.status === "−" ? "no" : "nz"
                }`}
              >
                {ind.status}
              </span>
            </div>
          ))}
        </div>
      </div>

      <div className="pl-arrow" aria-hidden="true">
        →
      </div>

      <div className="pl-stage">
        <div className="pl-cap">
          <span className="pl-num">04</span> Уровень
        </div>
        <div className="pl-box pl-result">
          <div className="pl-comp">ЭФФЕКТИВНАЯ КОММУНИКАЦИЯ</div>
          <div className="pl-level">
            2,0<small>из 3</small>
          </div>
          <div className="pl-track">
            <div className="pl-fill" />
          </div>
          <div className="pl-note">3 из 4 замеренных индикаторов — «+»</div>
        </div>
      </div>
    </div>
  );
}
