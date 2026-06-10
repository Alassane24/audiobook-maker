// Deco sunburst: 24 gold rays that slowly rotate behind the play
// roundel — the player's one piece of pure theater.
export function Sunburst({ size = 132 }: { size?: number }) {
  const rays = Array.from({ length: 24 }, (_, i) => {
    const a = (i / 24) * Math.PI * 2;
    const r1 = 44;
    const r2 = i % 2 === 0 ? 62 : 54; // alternating long/short rays
    return {
      x1: 66 + Math.cos(a) * r1,
      y1: 66 + Math.sin(a) * r1,
      x2: 66 + Math.cos(a) * r2,
      y2: 66 + Math.sin(a) * r2,
    };
  });
  return (
    <svg className="sunburst" width={size} height={size} viewBox="0 0 132 132" fill="none" aria-hidden="true">
      {rays.map((r, i) => (
        <line key={i} x1={r.x1} y1={r.y1} x2={r.x2} y2={r.y2} stroke="currentColor" strokeWidth={i % 2 === 0 ? 1.5 : 1} strokeLinecap="round" />
      ))}
    </svg>
  );
}
