/*
 * All marketing copy, keyed by locale. The home page and /pricing exist in
 * English, Telugu and Hindi; every other page is English only for now.
 */

import { en, type Copy } from "./en";
import { hi } from "./hi";
import { te } from "./te";
import type { Locale } from "./types";

export type { Copy };
export type * from "./types";

export const locales: readonly Locale[] = ["en", "te", "hi"];

export const content: Record<Locale, Copy> = { en, te, hi };

/** English copy: the default for components rendered without a locale. */
export const copy = en;

/** Pages that exist in every locale, by their English path. */
export const localisedPaths = ["/", "/pricing"] as const;
export type LocalisedPath = (typeof localisedPaths)[number];

/** `/pricing` → `/te/pricing`; `/` → `/te`. English paths are unprefixed. */
export function localePath(locale: Locale, path: LocalisedPath): string {
  if (locale === "en") return path;
  return path === "/" ? `/${locale}` : `/${locale}${path}`;
}

/** BCP 47 tags used for hreflang (India-specific). */
export const hreflang: Record<Locale, string> = { en: "en-IN", te: "te-IN", hi: "hi-IN" };

/** Language switcher options. Each label is written in its own script. */
export const languageOptions: { locale: Locale; short: string; label: string }[] = [
  { locale: "en", short: "EN", label: "English" },
  { locale: "te", short: "తె", label: "తెలుగు" },
  { locale: "hi", short: "हि", label: "हिंदी" },
];
