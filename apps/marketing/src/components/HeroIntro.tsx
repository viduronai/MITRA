"use client";

import { useEffect } from "react";

const QUINT = "cubic-bezier(0.22, 1, 0.36, 1)";
const EXPO = "cubic-bezier(0.16, 1, 0.3, 1)";
const SWEEP = "cubic-bezier(0.7, 0, 0.2, 1)";

/**
 * Vexel entrance, once per load. The boot script in the layout adds
 * `html.intro` (hidden pre-state) only when Web Animations exist and motion is
 * allowed. We wait for fonts (max 900ms), play every piece with fill "both",
 * then drop the class, cancel the animations and mark data-intro="done".
 */
export function HeroIntro() {
  useEffect(() => {
    const html = document.documentElement;
    if (!html.classList.contains("intro")) {
      html.setAttribute("data-intro", "done");
      return;
    }
    const root = document.querySelector<HTMLElement>("[data-hero-root]");
    if (!root) return;
    const q = (name: string) => Array.from(root.querySelectorAll<HTMLElement>(`[data-hero="${name}"]`));

    let cancelled = false;
    const anims: Animation[] = [];

    const run = () => {
      if (cancelled) return;
      html.setAttribute("data-intro", "running");
      const logo = q("wordmark")[0];
      const k = Math.min(1, Math.max(0.65, (logo?.getBoundingClientRect().height ?? 23.5) / 23.5));
      const play = (
        el: HTMLElement | undefined,
        frames: Keyframe[],
        delay: number,
        duration: number,
        easing: string,
      ) => {
        if (!el) return;
        anims.push(el.animate(frames, { delay, duration, easing, fill: "both" }));
      };
      const rise = (px: number, extra: Keyframe = {}): Keyframe[] => [
        { opacity: 0, transform: `translateY(${px * k}px)`, ...extra },
        { opacity: 1, transform: "none" },
      ];

      play(logo, rise(-6), 60, 900, QUINT);
      play(q("hairline")[0], [{ transform: "scaleX(0)" }, { transform: "scaleX(1)" }], 180, 1000, SWEEP);
      for (const link of q("nav")) {
        play(link, rise(-4), link.hasAttribute("data-outer") ? 490 : 420, 700, QUINT);
      }
      play(
        q("badge")[0],
        [
          { opacity: 0, transform: "scale(0.9)" },
          { opacity: 1, transform: "scale(1.03)", offset: 0.7 },
          { opacity: 1, transform: "none" },
        ],
        120,
        1000,
        EXPO,
      );
      q("line").forEach((line, i) => {
        play(line, [{ transform: "translateY(104%)" }, { transform: "none" }], 200 + i * 90, 1100, EXPO);
      });
      play(
        q("hello")[0],
        [
          { opacity: 0.35, filter: "blur(4px)" },
          { opacity: 1, filter: "blur(0px)" },
        ],
        620,
        1200,
        EXPO,
      );
      play(q("sub")[0], rise(10), 700, 850, QUINT);
      play(q("primary")[0], rise(12, { transform: `translateY(${12 * k}px) scale(0.975)` }), 860, 900, EXPO);
      play(
        q("secondary")[0],
        [
          { opacity: 0, transform: `translateX(${18 * k}px)` },
          { opacity: 1, transform: "none" },
        ],
        960,
        900,
        EXPO,
      );
      play(q("cue")[0], [{ opacity: 0 }, { opacity: 1 }], 1400, 800, QUINT);

      Promise.all(anims.map((a) => a.finished))
        .catch(() => {})
        .then(() => {
          if (cancelled) return;
          html.classList.remove("intro");
          for (const a of anims) a.cancel();
          html.setAttribute("data-intro", "done");
        });
    };

    const fonts = document.fonts?.ready ?? Promise.resolve();
    const cap = new Promise((resolve) => setTimeout(resolve, 900));
    Promise.race([fonts, cap]).then(run);

    return () => {
      cancelled = true;
      for (const a of anims) a.cancel();
      html.classList.remove("intro");
    };
  }, []);

  return null;
}
