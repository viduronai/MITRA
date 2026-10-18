"use client";

import { motion } from "motion/react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTranslations } from "next-intl";
import { cn } from "@/lib/utils";
import { isActive, primaryNav } from "./nav-items";

/** Mobile (<768px) bottom tab bar: Home · Calls · Team · Customers · More. */
export function BottomNav() {
  const t = useTranslations("nav");
  const pathname = usePathname();

  return (
    <nav
      aria-label={t("label")}
      className="fixed inset-x-0 bottom-0 z-40 border-t bg-surface/95 pb-[env(safe-area-inset-bottom)] backdrop-blur-md supports-backdrop-filter:bg-surface/85 md:hidden"
    >
      <ul className="mx-auto grid h-16 max-w-lg grid-cols-5">
        {primaryNav.map((item) => {
          const Icon = item.icon;
          const active = isActive(pathname, item.href);
          return (
            <li key={item.key} className="flex">
              <Link
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "focus-ring relative flex flex-1 flex-col items-center justify-center gap-0.5 rounded-lg text-[11px] leading-4 font-medium transition-colors motion-fast [&:lang(hi)]:text-[12.5px] [&:lang(te)]:text-[12.5px]",
                  active ? "text-brand-700" : "text-text-muted",
                )}
              >
                <span className="relative flex h-8 w-14 items-center justify-center">
                  {active && (
                    <motion.span
                      layoutId="bottom-nav-active"
                      className="absolute inset-0 rounded-full bg-brand-50"
                      transition={{ type: "spring", stiffness: 380, damping: 30 }}
                    />
                  )}
                  <Icon className="relative size-5" strokeWidth={active ? 2 : 1.75} aria-hidden />
                </span>
                <span className="max-w-full truncate px-0.5">{t(item.key)}</span>
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
