type Props = { className?: string; size?: number | string };

/** The mitra mark: an ink rounded square holding a sky sound wave. */
export function MitraMark({ className, size = 24 }: Props) {
  return (
    <svg className={className} width={size} height={size} viewBox="0 0 64 64" aria-hidden="true" focusable="false">
      <rect width="64" height="64" rx="16" fill="#05070d" />
      <rect x="0.5" y="0.5" width="63" height="63" rx="15.5" fill="none" stroke="#38c6f4" strokeOpacity=".35" />
      <g stroke="#38c6f4" strokeWidth="4.6" strokeLinecap="round">
        <path d="M14 28v8" />
        <path d="M23 22v20" />
        <path d="M32 15v34" />
        <path d="M41 22v20" />
        <path d="M50 28v8" />
      </g>
    </svg>
  );
}

/** Mark + lowercase "mitra" in Host Grotesk. Inherits colour and font size. */
export function Wordmark({ className }: { className?: string }) {
  return (
    <span className={className} style={{ display: "inline-flex", alignItems: "center", gap: "0.42em" }}>
      <MitraMark size="1.18em" />
      <span style={{ fontWeight: 500, letterSpacing: "-0.045em", lineHeight: 1 }}>mitra</span>
    </span>
  );
}
