import type { Metadata } from "next";
import Link from "next/link";
import { Wordmark } from "@/components/Wordmark";
import { notFoundCopy as t } from "@/content/pages/not-found";
import { fontVariables } from "@/lib/fonts";
import s from "./not-found.module.css";
import "./globals.css";

// Unmatched URLs across all three root layouts (en / te / hi) land here.
export const metadata: Metadata = {
  title: t.metaTitle,
  description: t.metaDescription,
  robots: { index: false, follow: true },
};

export default function GlobalNotFound() {
  return (
    <html lang="en-IN" className={fontVariables}>
      <body>
        <main className={`${s.page} grain`}>
          <div className={s.horizon} aria-hidden="true" />
          <Link href="/" className={s.logo} aria-label={t.home}>
            <Wordmark />
          </Link>
          <div className={s.copy}>
            <p className={s.code} aria-hidden="true">
              404
            </p>
            <p className={s.eyebrow}>{t.eyebrow}</p>
            <h1 className={s.title}>
              {t.titleBefore}
              <em className="accent">{t.titleAccent}</em>
            </h1>
            <p className={s.text}>{t.text}</p>
            <nav className={s.links} aria-label={t.linksLabel}>
              {t.links.map((l, i) => (
                <Link key={l.href} href={l.href} className={`btn ${i === 0 ? "btn-solid" : "btn-ghost"}`}>
                  {l.label}
                </Link>
              ))}
            </nav>
            <p className={s.lang}>
              {t.localised.map((l) => (
                <a key={l.href} href={l.href} lang={l.lang} hrefLang={l.lang}>
                  {l.label}
                </a>
              ))}
            </p>
          </div>
        </main>
      </body>
    </html>
  );
}
