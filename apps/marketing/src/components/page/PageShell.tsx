import { content, type Locale, type LocalisedPath } from "@/content";
import { CompactHeader } from "../CompactHeader";
import { Footer } from "../Footer";
import { languageHrefs } from "../LangSwitch";

type Props = {
  /** This page's own path (for the language switcher on English-only pages). */
  path: string;
  locale?: Locale;
  /** Set when the page exists in every locale. */
  localised?: LocalisedPath;
  children: React.ReactNode;
};

/**
 * Header + main + footer for every page except home. There is no hero
 * masthead here, so the glass bar is always shown, and "Call me now" leads to
 * the live demo on the (localised) home page.
 */
export function PageShell({ path, locale = "en", localised, children }: Props) {
  const copy = content[locale];
  const langHrefs = languageHrefs(locale, path, localised);
  const demoHref = `${copy.homeHref}#demo`;
  return (
    <>
      <CompactHeader copy={copy} langHrefs={langHrefs} always homeHref={copy.homeHref} ctaHref={demoHref} />
      <main id="main" tabIndex={-1}>
        {children}
      </main>
      <Footer copy={copy} langHrefs={langHrefs} homeHref={copy.homeHref} ctaHref={demoHref} />
    </>
  );
}
