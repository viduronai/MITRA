import { useTranslations } from "next-intl";
import { LiveDot } from "@/components/mitra/live-dot";
import { business, employee } from "@/lib/mock-data";
import { LanguageSwitcher } from "./language-switcher";
import { ThemeToggle } from "./theme-toggle";

/** Business name + "Priya is working · 2 calls live" + language & theme. */
export function AppHeader() {
  const t = useTranslations("header");
  const working = employee.status === "working";

  return (
    <header className="sticky top-0 z-30 border-b bg-bg/90 backdrop-blur-md supports-backdrop-filter:bg-bg/75">
      <div className="mx-auto flex h-16 max-w-[1200px] items-center gap-3 px-4 md:h-[72px] md:px-8">
        <div className="min-w-0 flex-1">
          <p className="truncate font-display text-base leading-6 font-semibold md:text-lg">{business.name}</p>
          <p className="flex items-center gap-2 text-[13px] leading-5 text-text-muted">
            {working && employee.liveCalls > 0 ? (
              <LiveDot />
            ) : (
              <span className="size-2 rounded-full bg-text-subtle" aria-hidden />
            )}
            <span className="truncate">
              {working ? t("isWorking", { name: employee.name }) : t("isPaused", { name: employee.name })}
              {working && (
                <>
                  <span aria-hidden> · </span>
                  <span className="sr-only">, </span>
                  {t("callsLive", { count: employee.liveCalls })}
                </>
              )}
            </span>
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-0.5">
          <LanguageSwitcher />
          <ThemeToggle />
        </div>
      </div>
    </header>
  );
}
