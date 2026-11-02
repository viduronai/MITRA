import type { Metadata } from "next";
import { hreflang, localePath, locales, type Locale, type LocalisedPath } from "@/content";
import { siteUrl } from "./site";

const ogLocale: Record<Locale, string> = { en: "en_IN", te: "te_IN", hi: "hi_IN" };

/** Shared by every root layout: base URL, title template, app name. */
export function rootMetadata(locale: Locale, title: string, description: string): Metadata {
  return {
    metadataBase: new URL(siteUrl),
    title: { default: title, template: "%s · Mitra" },
    description,
    applicationName: "Mitra",
    openGraph: { type: "website", siteName: "Mitra", locale: ogLocale[locale] },
    twitter: { card: "summary_large_image" },
  };
}

/** hreflang map for a page that exists in every locale. */
export function languageAlternates(path: LocalisedPath): Record<string, string> {
  const map: Record<string, string> = {};
  for (const l of locales) map[hreflang[l]] = localePath(l, path);
  map["x-default"] = localePath("en", path);
  return map;
}

type PageMeta = {
  /** Short page title; the layout template appends " · Mitra". */
  title: string;
  description: string;
  path: string;
  locale?: Locale;
  /** Set for pages that exist in te/hi too: adds hreflang alternates. */
  localised?: LocalisedPath;
  /** Use the title as-is (home pages). */
  absolute?: boolean;
  noindex?: boolean;
};

export function pageMetadata({
  title,
  description,
  path,
  locale = "en",
  localised,
  absolute = false,
  noindex = false,
}: PageMeta): Metadata {
  const fullTitle = absolute ? title : `${title} · Mitra`;
  return {
    title: absolute ? { absolute: title } : title,
    description,
    alternates: {
      canonical: path,
      languages: localised ? languageAlternates(localised) : undefined,
    },
    openGraph: {
      type: "website",
      siteName: "Mitra",
      locale: ogLocale[locale],
      title: fullTitle,
      description,
      url: path,
    },
    twitter: { card: "summary_large_image", title: fullTitle, description },
    robots: noindex ? { index: false, follow: true } : undefined,
  };
}
