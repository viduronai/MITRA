"use client";

import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { MitraMark, MitraWordmark } from "./mitra-logo";
import { isActive, primaryNav, upcomingNav, type NavItem } from "./nav-items";

/** Desktop (≥768px) navigation. Collapses to an icon rail. */
export function Sidebar() {
  const t = useTranslations("nav");
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);
  // Only the most specific match is highlighted (e.g. Connect, not also More, on /more/connect).
  const activeHref = [...primaryNav, ...upcomingNav]
    .filter((item) => (item.ready ?? true) && isActive(pathname, item.href))
    .sort((a, b) => b.href.length - a.href.length)[0]?.href;

  function renderItem(item: NavItem, disabled: boolean) {
    const Icon = item.icon;
    const label = t(item.key);
    const active = !disabled && item.href === activeHref;
    const classes = cn(
      "flex h-11 items-center gap-3 rounded-lg px-3 text-[15px] font-medium transition-colors motion-fast",
      collapsed && "justify-center px-0",
      active ? "bg-brand-50 text-brand-700" : "text-text-muted",
      !active && !disabled && "hover:bg-surface-2 hover:text-foreground",
      disabled && "cursor-not-allowed opacity-60",
    );

    const content = (
      <>
        <Icon className="size-5 shrink-0" strokeWidth={1.75} aria-hidden />
        {!collapsed && <span className="flex-1 truncate">{label}</span>}
        {!collapsed && disabled && (
          <span className="rounded-full bg-sky-100 px-2 py-0.5 text-[11px] leading-4 font-semibold text-sky-ink">
            {t("soon")}
          </span>
        )}
      </>
    );

    const element = disabled ? (
      // Not a link yet: these screens arrive in P2.
      <span role="link" aria-disabled="true" tabIndex={collapsed ? 0 : -1} className={classes}>
        {content}
        {collapsed && <span className="sr-only">{`${label} · ${t("soon")}`}</span>}
      </span>
    ) : (
      <Link href={item.href} aria-current={active ? "page" : undefined} className={classes}>
        {content}
        {collapsed && <span className="sr-only">{label}</span>}
      </Link>
    );

    return (
      <li key={item.key}>
        {collapsed ? (
          <Tooltip>
            <TooltipTrigger asChild>{element}</TooltipTrigger>
            <TooltipContent side="right">{disabled ? `${label} · ${t("soon")}` : label}</TooltipContent>
          </Tooltip>
        ) : (
          element
        )}
      </li>
    );
  }

  return (
    <aside
      className={cn(
        "sticky top-0 hidden h-dvh shrink-0 flex-col border-r bg-sidebar transition-[width] motion-slow md:flex",
        collapsed ? "w-[76px]" : "w-64",
      )}
    >
      <Link
        href="/"
        aria-label={t("brand")}
        className={cn("flex h-16 items-center gap-2.5 px-5", collapsed && "justify-center px-0")}
      >
        <MitraMark />
        {!collapsed && <MitraWordmark />}
      </Link>

      <nav aria-label={t("label")} className="flex-1 overflow-y-auto px-3 py-2">
        <ul className="flex flex-col gap-1">{primaryNav.map((item) => renderItem(item, false))}</ul>
        <div className="mx-3 my-4 h-px bg-border" role="separator" />
        <ul className="flex flex-col gap-1">{upcomingNav.map((item) => renderItem(item, !item.ready))}</ul>
      </nav>

      <div className={cn("p-3", collapsed && "flex justify-center")}>
        <Button
          variant="ghost"
          size="icon"
          onClick={() => setCollapsed((value) => !value)}
          aria-label={collapsed ? t("expand") : t("collapse")}
          aria-expanded={!collapsed}
          className="text-text-muted"
        >
          {collapsed ? <PanelLeftOpen aria-hidden /> : <PanelLeftClose aria-hidden />}
        </Button>
      </div>
    </aside>
  );
}
