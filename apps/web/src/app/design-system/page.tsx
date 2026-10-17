import type { Metadata } from "next";
import Link from "next/link";
import { Controls } from "@/components/design-system/controls";
import { Foundations } from "@/components/design-system/foundations";
import { MitraShowcase } from "@/components/design-system/mitra-showcase";
import { LanguageSwitcher } from "@/components/shell/language-switcher";
import { MitraMark, MitraWordmark } from "@/components/shell/mitra-logo";
import { ThemeToggle } from "@/components/shell/theme-toggle";

export const metadata: Metadata = {
  title: "Design system",
  description: "Mitra UI tokens and components — a living reference for designers and developers.",
};

const sections = [
  { id: "colour", label: "Colour" },
  { id: "type", label: "Type" },
  { id: "shape", label: "Shape & motion" },
  { id: "buttons", label: "Buttons" },
  { id: "inputs", label: "Inputs" },
  { id: "primitives", label: "Base" },
  { id: "mitra", label: "Mitra" },
];

// Internal reference page (outside the app shell). Copy is English on purpose.
export default function DesignSystemPage() {
  return (
    <div className="min-h-dvh">
      <header className="sticky top-0 z-30 border-b bg-bg/90 backdrop-blur-md supports-backdrop-filter:bg-bg/75">
        <div className="mx-auto flex h-16 max-w-[1200px] items-center gap-3 px-4 md:px-8">
          <Link href="/" className="flex items-center gap-2.5" aria-label="Back to the app">
            <MitraMark />
            <MitraWordmark />
          </Link>
          <span className="rounded-full bg-surface-2 px-2.5 py-0.5 text-xs font-medium text-text-muted">Design system</span>
          <div className="ml-auto flex items-center gap-0.5">
            <LanguageSwitcher />
            <ThemeToggle />
          </div>
        </div>
        <nav aria-label="Sections" className="mx-auto max-w-[1200px] overflow-x-auto px-4 md:px-8">
          <ul className="flex gap-1 pb-2">
            {sections.map((section) => (
              <li key={section.id}>
                <a
                  href={`#${section.id}`}
                  className="focus-ring inline-flex h-9 items-center rounded-full px-3 text-sm font-medium whitespace-nowrap text-text-muted transition-colors motion-fast hover:bg-surface-2 hover:text-foreground"
                >
                  {section.label}
                </a>
              </li>
            ))}
          </ul>
        </nav>
      </header>

      <main className="mx-auto flex max-w-[1200px] flex-col gap-14 px-4 py-10 md:gap-20 md:px-8 md:py-14">
        <div>
          <h1 className="text-[28px] leading-[34px] font-semibold tracking-tight md:text-4xl md:leading-[42px]">
            Mitra UI
          </h1>
          <p className="mt-2 max-w-2xl text-[17px] leading-[26px] text-text-muted">
            Clean, neat, premium, calm. Tokens live in <code className="font-mono text-sm">src/app/globals.css</code>;
            the rules are in <code className="font-mono text-sm">docs/06-DESIGN-SYSTEM.md</code>.
          </p>
        </div>
        <Foundations />
        <Controls />
        <MitraShowcase />
      </main>
    </div>
  );
}
