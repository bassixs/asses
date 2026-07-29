/**
 * Animated audio waveform — the signature motion of the product (the "как это работает"
 * bars everyone likes). Pure CSS; bars pulse with a staggered delay so the wave ripples
 * across. Decorative only (aria-hidden), disabled under prefers-reduced-motion.
 */
export function Waveform({
  bars = 44,
  className = "",
}: {
  bars?: number;
  className?: string;
}) {
  // A stable pseudo-random envelope: tall in the middle, jittered, so it reads as a real
  // waveform rather than a smooth curve. Deterministic — same shape every render.
  const heights = Array.from({ length: bars }, (_, i) => {
    const t = i / (bars - 1);
    const envelope = Math.sin(t * Math.PI); // 0 → 1 → 0
    const jitter = ((Math.sin(i * 12.9898) * 43758.5453) % 1 + 1) % 1; // 0..1 stable
    return Math.round((14 + 86 * envelope * (0.45 + 0.55 * jitter)));
  });

  return (
    <div className={`wf ${className}`} aria-hidden="true">
      {heights.map((h, i) => (
        <span
          key={i}
          style={{
            height: `${h}%`,
            animationDelay: `${(i % 12) * 90}ms`,
            animationDuration: `${1400 + (i % 5) * 120}ms`,
          }}
        />
      ))}
    </div>
  );
}
