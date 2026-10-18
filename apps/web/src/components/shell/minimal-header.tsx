import Link from "next/link";
import { LanguageSwitcher } from "./language-switcher";
import { MitraMark, MitraWordmark } from "./mitra-logo";
import { ThemeToggle } from "./theme-toggle";

/** Logo + language/theme, for screens outside the app shell (login, onboarding). */
export function MinimalHeader({ homeHref, homeLabel, children }: { homeHref: string; homeLabel: string; children?: React.ReactNode }) {
  return (
    <header className="sticky top-0 z-30 border-b bg-bg/90 backdrop-blur-md supports-backdrop-filter:bg-bg/75">
      <div className="mx-auto flex h-16 max-w-[1200px] items-center gap-3 px-4 md:px-8">
        <Link href={homeHref} aria-label={homeLabel} className="focus-ring flex h-11 items-center gap-2.5 rounded-lg">
          <MitraMark />
          <MitraWordmark />
        </Link>
        <div className="ml-auto flex shrink-0 items-center gap-0.5">
          <LanguageSwitcher />
          <ThemeToggle />
          {children}
        </div>
      </div>
    </header>
  );
}
