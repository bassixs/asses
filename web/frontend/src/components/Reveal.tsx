import { useEffect, useRef, useState, type ReactNode } from "react";

/** Users who ask for less motion get the content, not the choreography. */
export const reducedMotion = () =>
  typeof window !== "undefined" &&
  window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

/** Fades a block in the first time it scrolls into view. */
export function Reveal({
  children,
  delay = 0,
  className = "",
}: {
  children: ReactNode;
  delay?: number;
  className?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [shown, setShown] = useState(reducedMotion());

  useEffect(() => {
    if (shown || !ref.current) return;

    // Safety net: content must never stay invisible because the observer did not
    // fire (unsupported API, a tab that never painted, layout quirks). Decoration
    // may fail; the page still has to be readable.
    const fallback = window.setTimeout(() => setShown(true), 1500);

    if (typeof IntersectionObserver === "undefined") {
      setShown(true);
      return () => window.clearTimeout(fallback);
    }

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setShown(true);
          observer.disconnect();
        }
      },
      { threshold: 0.15 },
    );
    observer.observe(ref.current);
    return () => {
      window.clearTimeout(fallback);
      observer.disconnect();
    };
  }, [shown]);

  return (
    <div
      ref={ref}
      className={`reveal ${shown ? "in" : ""} ${className}`}
      style={{ transitionDelay: `${delay}ms` }}
    >
      {children}
    </div>
  );
}

/** Counts up to `value` once, easing out. `decimals` keeps fractional values (e.g. 1.9). */
export function useCountUp(value: number, duration = 1100, decimals = 0): number {
  const [shown, setShown] = useState(reducedMotion() ? value : 0);

  useEffect(() => {
    if (reducedMotion() || value <= 0) {
      setShown(value);
      return;
    }
    const factor = Math.pow(10, decimals);
    let frame = 0;
    let done = false;
    const start = performance.now();
    const tick = (now: number) => {
      const progress = Math.min(1, (now - start) / duration);
      // easeOutCubic — fast first, gentle landing
      setShown(Math.round(value * (1 - Math.pow(1 - progress, 3)) * factor) / factor);
      if (progress < 1) frame = requestAnimationFrame(tick);
      else done = true;
    };
    frame = requestAnimationFrame(tick);

    // rAF never fires in a tab that is not painting — without this the counter
    // would sit at 0 and report numbers that are simply wrong.
    const fallback = window.setTimeout(() => {
      if (!done) setShown(value);
    }, duration + 400);

    return () => {
      cancelAnimationFrame(frame);
      window.clearTimeout(fallback);
    };
  }, [value, duration, decimals]);

  return shown;
}

/** Inline animated number. */
export function CountUp({ value, decimals = 0 }: { value: number; decimals?: number }) {
  const shown = useCountUp(value, 1100, decimals);
  return <>{shown.toFixed(decimals)}</>;
}
