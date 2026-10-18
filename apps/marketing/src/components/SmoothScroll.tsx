"use client";

import Lenis from "lenis";
import { useEffect } from "react";

/**
 * Lenis smooth scroll for the whole page, plus the one shared observer that
 * flips `[data-reveal]` blocks to `data-in` when they enter the viewport.
 * Lenis is skipped under prefers-reduced-motion; reveals still run (CSS turns
 * them into instant state changes).
 */
export function SmoothScroll() {
  useEffect(() => {
    const reveals = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue;
          entry.target.setAttribute("data-in", "");
          reveals.unobserve(entry.target);
        }
      },
      { rootMargin: "0px 0px -12% 0px", threshold: 0.01 },
    );
    document.querySelectorAll("[data-reveal]").forEach((el) => reveals.observe(el));

    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)");
    let lenis: Lenis | null = null;
    let raf = 0;
    let idle = 0;
    let disposed = false;
    const start = () => {
      if (disposed || reduce.matches) return;
      lenis = new Lenis({ anchors: { offset: 0 }, lerp: 0.11, wheelMultiplier: 1 });
      window.__mitraLenis = lenis;
      const loop = (time: number) => {
        lenis?.raf(time);
        raf = requestAnimationFrame(loop);
      };
      raf = requestAnimationFrame(loop);
    };
    // Smooth scroll is an enhancement: start it once the page has loaded.
    const schedule = () => {
      if (typeof window.requestIdleCallback === "function") idle = window.requestIdleCallback(start, { timeout: 2000 });
      else start();
    };
    if (document.readyState === "complete") schedule();
    else window.addEventListener("load", schedule, { once: true });

    return () => {
      disposed = true;
      window.removeEventListener("load", schedule);
      if (idle) window.cancelIdleCallback(idle);
      reveals.disconnect();
      cancelAnimationFrame(raf);
      lenis?.destroy();
      window.__mitraLenis = undefined;
    };
  }, []);

  return null;
}
