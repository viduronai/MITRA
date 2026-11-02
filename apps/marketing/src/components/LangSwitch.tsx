import { languageOptions, localePath, type Locale, type LocalisedPath } from "@/content";
import s from "./lang.module.css";

/**
 * Where each language option leads from the current page: the same page in
 * that language when it is localised, otherwise that language's home page.
 */
export function languageHrefs(current: Locale, path: string, localised?: LocalisedPath): Record<Locale, string> {
  return {
    en: localised ? localePath("en", localised) : current === "en" ? path : "/",
    te: localePath("te", localised ?? "/"),
    hi: localePath("hi", localised ?? "/"),
  };
}

type Props = {
  current: Locale;
  hrefs: Record<Locale, string>;
  label: string;
  tone?: "dark" | "light";
  className?: string;
} & React.HTMLAttributes<HTMLElement>;

/** EN · తె · हि. Each option is labelled in its own script and language. */
export function LangSwitch({ current, hrefs, label, tone = "dark", className, ...rest }: Props) {
  return (
    <nav aria-label={label} className={`${s.switch} ${className ?? ""}`} data-tone={tone} {...rest}>
      {languageOptions.map((o) => (
        <a
          key={o.locale}
          href={hrefs[o.locale]}
          hrefLang={o.locale}
          lang={o.locale}
          aria-label={o.label}
          aria-current={o.locale === current ? "page" : undefined}
          className={s.option}
        >
          {o.short}
        </a>
      ))}
    </nav>
  );
}
