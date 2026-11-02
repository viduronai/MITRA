import { fontVariables } from "@/lib/fonts";
import { SmoothScroll } from "./SmoothScroll";
import "../app/globals.css";

// Runs before first paint: marks JS as available and arms the hero entrance
// (Vexel). If the entrance has not started within 3.5s the class is removed so
// the hero can never stay hidden (and pages without a hero lose it harmlessly).
const bootScript = `(function(){var d=document.documentElement;d.classList.add('js');try{if(!matchMedia('(prefers-reduced-motion: reduce)').matches&&typeof d.animate==='function'){d.classList.add('intro');setTimeout(function(){if(!d.getAttribute('data-intro'))d.classList.remove('intro')},3500)}}catch(e){}})();`;

/**
 * The <html> document shared by the per-locale root layouts (`app/(en)`,
 * `app/te`, `app/hi`), so each locale gets a correct `lang` attribute.
 */
export function RootShell({ lang, skip, children }: { lang: string; skip: string; children: React.ReactNode }) {
  return (
    <html lang={lang} className={fontVariables} suppressHydrationWarning>
      {/* eslint-disable-next-line @next/next/no-head-element -- App Router root layout markup, not pages/ */}
      <head>
        <script dangerouslySetInnerHTML={{ __html: bootScript }} />
        <link rel="preconnect" href="https://d8j0ntlcm91z4.cloudfront.net" crossOrigin="anonymous" />
      </head>
      <body>
        <a className="skip-link" href="#main">
          {skip}
        </a>
        {children}
        <SmoothScroll />
      </body>
    </html>
  );
}
