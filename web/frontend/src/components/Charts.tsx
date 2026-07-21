import type { ReactNode } from "react";
import { useCountUp } from "./Reveal";

/** Big headline metric. */
export function StatTile({
  label,
  value,
  hint,
  accent,
}: {
  label: string;
  value: ReactNode;
  hint?: string;
  accent?: boolean;
}) {
  return (
    <div className={`stat ${accent ? "stat-accent" : ""}`}>
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
      {hint && <div className="stat-hint">{hint}</div>}
    </div>
  );
}

/** Horizontal bars, single series (magnitude). Value rides the tip; count in the tooltip. */
export function BarList({
  data,
  max,
}: {
  data: { name: string; value: number; count?: number }[];
  max: number;
}) {
  if (data.length === 0) return <p className="muted">Пока нет данных для графика.</p>;
  return (
    <div className="barlist">
      {data.map((d) => {
        const pct = max > 0 ? Math.max(2, Math.min(100, (d.value / max) * 100)) : 0;
        return (
          <div
            className="barrow"
            key={d.name}
            title={d.count != null ? `${d.name}: ${d.value.toFixed(1)} · измерений: ${d.count}` : undefined}
          >
            <div className="barlabel">{d.name}</div>
            <div className="bartrack">
              <div className="barfill" style={{ width: `${pct}%` }} />
            </div>
            <div className="barvalue">{d.value.toFixed(1)}</div>
          </div>
        );
      })}
    </div>
  );
}

const BAND_CLASS = ["band-none", "band-low", "band-ok", "band-high"];

/** Distribution across the ordered ТЗ level bands — a 100%-stacked bar + legend. */
export function BandBar({ data }: { data: { name: string; count: number }[] }) {
  const total = data.reduce((s, d) => s + d.count, 0);
  if (total === 0) return <p className="muted">Пока нет измерений для распределения.</p>;
  return (
    <div className="bandbar">
      <div className="bandtrack">
        {data.map((d, i) =>
          d.count === 0 ? null : (
            <div
              key={d.name}
              className={`bandseg ${BAND_CLASS[i] ?? ""}`}
              style={{ flexGrow: d.count, animationDelay: `${i * 140}ms` }}
              title={`${d.name}: ${d.count} (${Math.round((d.count / total) * 100)}%)`}
            />
          ),
        )}
      </div>
      <div className="bandlegend">
        {data.map((d, i) => (
          <div className="bandkey" key={d.name}>
            <span className={`dot ${BAND_CLASS[i] ?? ""}`} />
            <span className="bandkey-name">{d.name}</span>
            <span className="bandkey-num">{d.count}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

/** Radial gauge for the overall average level (0..max). One hero figure. */
export function Gauge({ value, max, caption }: { value: number; max: number; caption: string }) {
  const r = 62;
  const cx = 80;
  const cy = 80;
  const start = 135; // degrees, sweep 270° clockwise
  const sweep = 270;
  const frac = max > 0 ? Math.max(0, Math.min(1, value / max)) : 0;

  const polar = (deg: number) => {
    const rad = ((deg - 90) * Math.PI) / 180;
    return [cx + r * Math.cos(rad), cy + r * Math.sin(rad)];
  };
  const arc = (fromDeg: number, toDeg: number) => {
    const [x1, y1] = polar(fromDeg);
    const [x2, y2] = polar(toDeg);
    const large = toDeg - fromDeg > 180 ? 1 : 0;
    return `M ${x1} ${y1} A ${r} ${r} 0 ${large} 1 ${x2} ${y2}`;
  };

  const shown = useCountUp(value, 1200, 1);

  return (
    <div className="gauge">
      <svg viewBox="0 0 160 160" width="160" height="160" role="img" aria-label={`${caption}: ${value} из ${max}`}>
        <path className="gauge-track" d={arc(start, start + sweep)} />
        {frac > 0 && (
          // pathLength=1 lets CSS draw any-length arc via a single stroke-dashoffset sweep.
          <path className="gauge-fill" pathLength={1} d={arc(start, start + sweep * frac)} />
        )}
        <text x="80" y="76" className="gauge-num">{shown.toFixed(1)}</text>
        <text x="80" y="98" className="gauge-max">из {max}</text>
      </svg>
      <div className="gauge-caption">{caption}</div>
    </div>
  );
}
