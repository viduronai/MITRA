"use client";

import { useEffect, useRef, useState } from "react";

type Props = {
  src: string;
  poster?: string;
  className?: string;
  /** Load as soon as the page hydrates (the hero). Others wait until near the viewport. */
  eager?: boolean;
  onReady?: () => void;
};

type NetworkInformation = { saveData?: boolean; effectiveType?: string };

type Still = false | "reduced" | "data";

function prefersStill(): Still {
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return "reduced";
  const conn = (navigator as Navigator & { connection?: NetworkInformation }).connection;
  if (!conn) return false;
  return conn.saveData || /(^|-)2g$/.test(conn.effectiveType ?? "") ? "data" : false;
}

/**
 * Decorative looping video. Media rules (landing-direction §3): below-the-fold
 * videos stay unloaded until near the viewport; reduced motion, Save-Data and
 * 2G show the poster (or the scene's CSS gradient) instead; playback pauses
 * when off screen. Autoplay is retried on first interaction (Targo).
 */
export function LazyVideo({ src, poster, className, eager = false, onReady }: Props) {
  const ref = useRef<HTMLVideoElement>(null);
  const [active, setActive] = useState(false);
  const [still, setStill] = useState<Still>(false);

  useEffect(() => {
    const video = ref.current;
    if (!video) return;
    const mode = prefersStill();
    if (mode) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- reads browser-only preferences after mount
      setStill(mode);
      onReady?.();
      return;
    }

    const tryPlay = () => {
      video.muted = true;
      video.play().catch(() => {});
    };

    const io = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setActive(true);
          tryPlay();
        } else if (!video.paused) {
          video.pause();
        }
      },
      { rootMargin: eager ? "0px" : "0px 0px 35% 0px" },
    );
    // Nothing below the fold competes with the first paint.
    const observe = () => io.observe(video);
    if (eager || document.readyState === "complete") observe();
    else window.addEventListener("load", observe, { once: true });

    const kick = () => tryPlay();
    document.addEventListener("pointerdown", kick, { once: true, passive: true });
    return () => {
      io.disconnect();
      window.removeEventListener("load", observe);
      document.removeEventListener("pointerdown", kick);
    };
  }, [eager, onReady]);

  useEffect(() => {
    if (active && ref.current) {
      ref.current.muted = true;
      ref.current.play().catch(() => {});
    }
  }, [active]);

  if (still) {
    if (poster) {
      // eslint-disable-next-line @next/next/no-img-element -- remote decorative poster, sized by CSS
      return <img src={poster} alt="" aria-hidden="true" className={className} loading="lazy" decoding="async" />;
    }
    // Reduced motion without a poster: a paused first frame keeps the visual
    // without movement. Save-Data gets nothing (the scene's CSS fallback).
    return still === "reduced" ? (
      <video
        className={className}
        src={`${src}#t=0.5`}
        muted
        playsInline
        preload="metadata"
        aria-hidden="true"
        tabIndex={-1}
      />
    ) : null;
  }

  return (
    <video
      ref={ref}
      className={className}
      src={active ? src : undefined}
      muted
      loop
      playsInline
      autoPlay
      preload={active ? "auto" : "none"}
      aria-hidden="true"
      tabIndex={-1}
      disablePictureInPicture
      onLoadedData={onReady}
    />
  );
}
