// Doto has no ₹ glyph, so the rupee is drawn on the same 5×7 dot grid.
const RUPEE = ["11111", "00010", "11111", "01100", "00100", "00010", "00001"];

export function RupeeDots({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 5 7" aria-hidden="true">
      {RUPEE.flatMap((row, y) =>
        row
          .split("")
          .map((on, x) =>
            on === "1" ? (
              <rect key={`${x}-${y}`} x={x + 0.11} y={y + 0.11} width="0.78" height="0.78" rx="0.14" />
            ) : null,
          ),
      )}
    </svg>
  );
}
