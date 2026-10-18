"use client";

/** Picks a scenario in "Hear it" and scrolls there. */
export function SampleButton({
  scenario,
  label,
  industry,
  className,
  children,
}: {
  scenario: string;
  label: string;
  industry: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      className={className}
      aria-label={`${label}: ${industry}`}
      onClick={() => {
        window.dispatchEvent(new CustomEvent("mitra:play-scenario", { detail: scenario }));
        const target = document.getElementById("hear");
        if (!target) return;
        if (window.__mitraLenis) window.__mitraLenis.scrollTo(target, { duration: 1.4 });
        else target.scrollIntoView({ behavior: "auto" });
      }}
    >
      {children}
    </button>
  );
}
