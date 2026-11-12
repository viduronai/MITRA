import type { MetadataRoute } from "next";
import { localePath, locales } from "@/content";
import { languageAlternates } from "@/lib/seo";
import { siteUrl } from "@/lib/site";

export const dynamic = "force-static";

// Privacy and Terms are drafts (noindex) until legal review, so not listed.
const englishOnly = [
  "/how-it-works",
  "/clinics",
  "/real-estate",
  "/education",
  "/agencies",
  "/safety",
  "/about",
];

const abs = (path: string) => new URL(path, siteUrl).toString();

/** Every public page; home and /pricing carry hreflang alternates for te / hi. */
export default function sitemap(): MetadataRoute.Sitemap {
  const localised = (["/", "/pricing"] as const).flatMap((path) =>
    locales.map((l) => ({
      url: abs(localePath(l, path)),
      changeFrequency: "weekly" as const,
      priority: path === "/" ? (l === "en" ? 1 : 0.9) : 0.8,
      alternates: {
        languages: Object.fromEntries(Object.entries(languageAlternates(path)).map(([k, v]) => [k, abs(v)])),
      },
    })),
  );
  const rest = englishOnly.map((path) => ({
    url: abs(path),
    changeFrequency: "monthly" as const,
    priority: 0.7,
  }));
  return [...localised, ...rest];
}
