import { useTranslations } from "next-intl";
import { LiveDot } from "@/components/mitra/live-dot";
import type { EmployeeStatus } from "@/lib/api/types";
import { cn } from "@/lib/utils";
import { LanguageSwitcher } from "./language-switcher";
import { ThemeToggle } from "./theme-toggle";

interface AppHeaderProps {
  businessName: string;
  employee: { name: string; status: EmployeeStatus } | null;
  /** MOCK until calls exist in the API. */
  liveCalls: number;
}

/** Business name + "Priya is working · 2 calls live" + language & theme. */
export function AppHeader({ businessName, employee, liveCalls }: AppHeaderProps) {
  const t = useTranslations("header");
  const working = employee?.status === "working";

  return (
    <header className="sticky top-0 z-30 border-b bg-bg/90 backdrop-blur-md supports-backdrop-filter:bg-bg/75">
      <div className="mx-auto flex min-h-16 max-w-[1200px] items-center gap-3 px-4 py-2 md:min-h-[72px] md:px-8">
        <div className="min-w-0 flex-1">
          <p className="truncate font-display text-base leading-6 font-semibold md:text-lg">{businessName}</p>
          <p className="flex items-start gap-2 text-[13px] leading-5 text-text-muted">
            {/* Green = working (same meaning as the Team badge). Sky LiveDot = on a call right now. */}
            <span
              className={cn("mt-1.5 size-2 shrink-0 rounded-full", working ? "bg-success" : employee?.status === "training" ? "bg-info" : "bg-text-subtle")}
              aria-hidden
            />
            <span className="line-clamp-2 min-w-0">
              {!employee
                ? t("setupPending")
                : employee.status === "training"
                  ? t("isTraining", { name: employee.name })
                  : working
                    ? t("isWorking", { name: employee.name })
                    : t("isPaused", { name: employee.name })}
              {working && liveCalls > 0 && (
                // Dropped under 400px so long Telugu/Hindi status lines still fit.
                <span className="hidden min-[400px]:inline">
                  <span aria-hidden> · </span>
                  <span className="sr-only">, </span>
                  <LiveDot className="mx-1 align-[-1px]" />
                  {t("callsLive", { count: liveCalls })}
                </span>
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
