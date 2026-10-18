"use client";

import { useEffect, useRef, useState } from "react";
import { media } from "@/lib/media";

/**
 * Vexel horizon video. The file is ~13 MB, so it starts loading only after the
 * page's `load` event and an idle slot: text and fonts paint first (LCP), then
 * the horizon fades in over the static gradient. Reduced motion and Save-Data
 * keep the gradient only.
 */
export function HeroVideo({ className }: { className?: string }) {
  const ref = useRef<HTMLVideoElement>(null);
  const [src, setSrc] = useState<string | undefined>(undefined);

  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const conn = (navigator as Navigator & { connection?: { saveData?: boolean; effectiveType?: string } }).connection;
    if (conn?.saveData || /(^|-)2g$/.test(conn?.effectiveType ?? "")) return;

    let idle = 0;
    let timer = 0;
    const start = () => {
      const go = () => setSrc(media.heroHorizon);
      if (typeof window.requestIdleCallback === "function") idle = window.requestIdleCallback(go, { timeout: 1500 });
      else timer = window.setTimeout(go, 300);
    };
    if (document.readyState === "complete") start();
    else window.addEventListener("load", start, { once: true });

    return () => {
      window.removeEventListener("load", start);
      if (idle) window.cancelIdleCallback(idle);
      clearTimeout(timer);
    };
  }, []);

  useEffect(() => {
    const video = ref.current;
    if (!video || !src) return;
    video.muted = true;
    video.play().catch(() => {});
    // Pause the loop while the hero is off screen.
    const io = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting) video.play().catch(() => {});
      else video.pause();
    });
    io.observe(video);
    return () => io.disconnect();
  }, [src]);

  return (
    <video
      ref={ref}
      className={className}
      src={src}
      autoPlay
      muted
      loop
      playsInline
      preload="auto"
      tabIndex={-1}
      disablePictureInPicture
      onLoadedData={(e) => {
        e.currentTarget.setAttribute("data-ready", "");
        window.dispatchEvent(new Event("mitra:hero-video"));
      }}
    />
  );
}
