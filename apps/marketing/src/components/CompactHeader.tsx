"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { content, type Copy, type Locale } from "@/content";
import { LangSwitch } from "./LangSwitch";
import { Wordmark } from "./Wordmark";
import s from "./header.module.css";

const FOCUSABLE = 'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])';

type Props = {
  copy?: Copy;
  /** Where the language switcher leads, per locale. */
  langHrefs: Record<Locale, string>;
  /** Sub-pages have no hero: the bar is always visible. */
  always?: boolean;
  homeHref?: string;
  ctaHref?: string;
};

/**
 * Sticky glass bar that takes over from the hero masthead once it scrolls
 * away (or is always shown on pages without a hero), plus the ECHOID
 * circular-reveal menu for ≤900px (dialog semantics, focus trap, Escape,
 * focus restore, auto-close on desktop widths).
 */
export function CompactHeader({
  copy = content.en,
  langHrefs,
  always = false,
  homeHref = "#top",
  ctaHref = "#demo",
}: Props) {
  const { nav } = copy;
  const [pastHero, setPastHero] = useState(false);
  const shown = always || pastHero;
  const [open, setOpen] = useState(false);
  const [light, setLight] = useState(false);
  const toggleRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const hero = document.getElementById("top");
    if (always || !hero) return;
    const io = new IntersectionObserver(([entry]) => setPastHero(!entry.isIntersecting), {
      rootMargin: "-72px 0px 0px 0px",
    });
    io.observe(hero);
    return () => io.disconnect();
  }, [always]);

  // Tone follows the section under the bar: light glass over chalk.
  useEffect(() => {
    let raf = 0;
    const probe = () => {
      raf = 0;
      const y = (document.querySelector<HTMLElement>("[data-bar]")?.offsetHeight ?? 64) + 2;
      const el = document.elementFromPoint(window.innerWidth / 2, y);
      setLight(Boolean(el?.closest(".on-chalk")));
    };
    const onScroll = () => {
      if (!raf) raf = requestAnimationFrame(probe);
    };
    probe();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
    };
  }, []);

  const close = useCallback((restoreFocus = true) => {
    setOpen(false);
    if (restoreFocus) toggleRef.current?.focus();
  }, []);

  // Menu side effects: origin of the circle, scroll lock, keyboard handling.
  useEffect(() => {
    const menu = menuRef.current;
    const toggle = toggleRef.current;
    if (!menu || !toggle) return;
    if (!open) {
      document.body.style.overflow = "";
      window.__mitraLenis?.start();
      return;
    }
    const r = toggle.getBoundingClientRect();
    menu.style.setProperty("--ox", `${r.left + r.width / 2}px`);
    menu.style.setProperty("--oy", `${r.top + r.height / 2}px`);
    document.body.style.overflow = "hidden";
    window.__mitraLenis?.stop();
    const first = menu.querySelector<HTMLElement>(FOCUSABLE);
    first?.focus({ preventScroll: true });

    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        close();
        return;
      }
      if (e.key !== "Tab") return;
      const items = [toggle, ...Array.from(menu.querySelectorAll<HTMLElement>(FOCUSABLE))];
      const idx = items.indexOf(document.activeElement as HTMLElement);
      const next = e.shiftKey ? (idx <= 0 ? items.length - 1 : idx - 1) : idx === items.length - 1 ? 0 : idx + 1;
      e.preventDefault();
      items[next]?.focus();
    };
    const desktop = window.matchMedia("(min-width: 901px)");
    const onDesktop = () => desktop.matches && close(false);
    document.addEventListener("keydown", onKey);
    desktop.addEventListener("change", onDesktop);
    return () => {
      document.removeEventListener("keydown", onKey);
      desktop.removeEventListener("change", onDesktop);
    };
  }, [open, close]);

  const visible = shown || open;

  return (
    <>
      <div
        className={s.bar}
        data-bar
        data-shown={visible ? "" : undefined}
        data-menu-open={open ? "" : undefined}
        data-tone={light && !open ? "light" : "dark"}
        inert={!visible}
      >
        <a href={homeHref} className={s.logo} aria-label={nav.home} onClick={() => open && close(false)}>
          <Wordmark />
        </a>
        <nav className={s.pills} aria-label="Primary">
          {nav.links.map((link) => (
            <a key={link.href} href={link.href} className={s.pill}>
              {link.label}
            </a>
          ))}
        </nav>
        <div className={s.right}>
          <LangSwitch
            className={s.lang}
            current={copy.locale}
            hrefs={langHrefs}
            label={nav.language}
            tone={light && !open ? "light" : "dark"}
          />
          <a href={ctaHref} className={`btn btn-solid ${s.cta}`} onClick={() => open && close(false)}>
            {nav.cta}
          </a>
          <button
            ref={toggleRef}
            type="button"
            className={s.burger}
            aria-expanded={open}
            aria-controls="site-menu"
            aria-label={open ? nav.closeMenu : nav.openMenu}
            onClick={() => (open ? close() : setOpen(true))}
          >
            <span />
            <span />
            <span />
          </button>
        </div>
      </div>

      <div
        ref={menuRef}
        id="site-menu"
        className={s.menu}
        role="dialog"
        aria-modal="true"
        aria-label={nav.menuLabel}
        aria-hidden={!open}
        inert={!open}
        data-open={open ? "" : undefined}
        onClick={(e) => {
          if (e.target === e.currentTarget) close();
        }}
      >
        {nav.links.map((link, i) => (
          <a
            key={link.href}
            href={link.href}
            className={s.menuLink}
            style={{ "--i": i } as React.CSSProperties}
            onClick={() => close(false)}
          >
            {link.label}
          </a>
        ))}
        <a
          href={ctaHref}
          className={s.menuCta}
          style={{ "--i": nav.links.length } as React.CSSProperties}
          onClick={() => close(false)}
        >
          {nav.cta}
        </a>
        <LangSwitch
          className={s.menuLang}
          current={copy.locale}
          hrefs={langHrefs}
          label={nav.language}
          style={{ "--i": nav.links.length + 1 } as React.CSSProperties}
        />
        <p className={s.menuNote}>{copy.hero.badge}</p>
      </div>
    </>
  );
}
