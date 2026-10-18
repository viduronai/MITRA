"use client";

import { useEffect, useRef } from "react";

export type VoiceSignal = {
  /** 0..1 target loudness; the sphere smooths it. */
  amp: number;
  who: "mitra" | "caller" | null;
};

type Props = { signal: React.RefObject<VoiceSignal>; className?: string };

const TAU = Math.PI * 2;

function sprite(rgb: [number, number, number], size: number): HTMLCanvasElement {
  const c = document.createElement("canvas");
  c.width = c.height = size;
  const g = c.getContext("2d")!;
  const grad = g.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
  const [r, gr, b] = rgb;
  grad.addColorStop(0, `rgba(${r},${gr},${b},1)`);
  grad.addColorStop(0.32, `rgba(${r},${gr},${b},0.85)`);
  grad.addColorStop(1, `rgba(${r},${gr},${b},0)`);
  g.fillStyle = grad;
  g.fillRect(0, 0, size, size);
  return c;
}

/**
 * The Voice Sphere: a Fibonacci sphere of glowing particles that ripples
 * outward from its front when Mitra speaks, shimmers whiter for the caller,
 * breathes when idle and leans toward the pointer. Canvas 2D, additive
 * blending, DPR-capped, 30fps on mobile, paused off screen, one still frame
 * under reduced motion.
 */
export default function VoiceSphere({ signal, className }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d", { alpha: true });
    if (!ctx) return;

    const mobile = window.matchMedia("(max-width: 767px), (pointer: coarse)").matches;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const count = mobile ? 900 : 2200;
    const frameMs = mobile ? 1000 / 30 : 1000 / 60;
    const dprCap = mobile ? 1.5 : 2;

    // Points on a unit sphere (golden-angle spiral).
    const base = new Float32Array(count * 3);
    const seed = new Float32Array(count);
    const golden = Math.PI * (3 - Math.sqrt(5));
    for (let i = 0; i < count; i++) {
      const y = 1 - (i / (count - 1)) * 2;
      const r = Math.sqrt(1 - y * y);
      const th = golden * i;
      base[i * 3] = Math.cos(th) * r;
      base[i * 3 + 1] = y;
      base[i * 3 + 2] = Math.sin(th) * r;
      seed[i] = Math.random() * TAU;
    }

    const skySprite = sprite([56, 198, 244], 32);
    const blueSprite = sprite([47, 107, 255], 32);
    const whiteSprite = sprite([214, 236, 255], 32);

    let w = 0;
    let h = 0;
    let dpr = 1;
    const resize = () => {
      const rect = canvas.getBoundingClientRect();
      dpr = Math.min(window.devicePixelRatio || 1, dprCap);
      w = Math.max(1, Math.round(rect.width * dpr));
      h = Math.max(1, Math.round(rect.height * dpr));
      canvas.width = w;
      canvas.height = h;
    };
    resize();
    // Resizing clears the canvas; the reduced-motion still frame must be redrawn.
    const ro = new ResizeObserver(() => {
      resize();
      if (reduce) draw(16);
    });
    ro.observe(canvas);

    let px = 0;
    let py = 0;
    let tx = 0;
    let ty = 0;
    const onPointer = (e: PointerEvent) => {
      tx = (e.clientX / window.innerWidth - 0.5) * 2;
      ty = (e.clientY / window.innerHeight - 0.5) * 2;
    };
    if (!mobile && !reduce) window.addEventListener("pointermove", onPointer, { passive: true });

    let amp = 0;
    let callerMix = 0;
    let rotY = 0.6;
    let t = 0;

    const draw = (dt: number) => {
      const sig = signal.current;
      const target = sig?.amp ?? 0;
      // Fast attack, slower release, like a VU meter.
      amp += (target - amp) * (target > amp ? 0.35 : 0.08);
      callerMix += ((sig?.who === "caller" ? 1 : 0) - callerMix) * 0.06;
      px += (tx - px) * 0.04;
      py += (ty - py) * 0.04;
      t += dt / 1000;
      rotY += (dt / 1000) * (0.16 + amp * 0.22);
      const rotX = -0.32 + py * 0.25;
      const yaw = rotY + px * 0.35;

      ctx.clearRect(0, 0, w, h);
      const cx = w / 2;
      const cy = h / 2;
      const R = Math.min(w, h) * 0.34;

      // Core glow.
      const glow = ctx.createRadialGradient(cx, cy, 0, cx, cy, R * 1.6);
      glow.addColorStop(0, `rgba(56,198,244,${0.1 + amp * 0.22})`);
      glow.addColorStop(0.45, `rgba(47,107,255,${0.05 + amp * 0.08})`);
      glow.addColorStop(1, "rgba(1,6,26,0)");
      ctx.fillStyle = glow;
      ctx.fillRect(0, 0, w, h);

      const sy = Math.sin(yaw);
      const cyw = Math.cos(yaw);
      const sx = Math.sin(rotX);
      const cxr = Math.cos(rotX);
      const persp = 2.8;
      const dot = 2.3 * dpr;

      ctx.globalCompositeOperation = "lighter";
      for (let i = 0; i < count; i++) {
        const bx = base[i * 3];
        const by = base[i * 3 + 1];
        const bz = base[i * 3 + 2];
        // Rotate the unit point: yaw (Y axis) then pitch (X axis).
        const ux = bx * cyw + bz * sy;
        const uz1 = -bx * sy + bz * cyw;
        const uy = by * cxr - uz1 * sx;
        const uz = by * sx + uz1 * cxr;
        // Ripple radiates from the pole facing the viewer, so the voice
        // always travels toward the visitor.
        const d = Math.acos(uz > 1 ? 1 : uz < -1 ? -1 : uz);
        const ripple = Math.sin(d * 7 - t * 9) * Math.exp(-d * 0.55);
        const breathe = Math.sin(t * 1.1 + seed[i]) * 0.012;
        const shimmer = callerMix * Math.sin(t * 13 + seed[i] * 3) * 0.03 * amp;
        const k = 1 + breathe + amp * 0.17 * ripple + shimmer;
        const x1 = ux * k;
        const y2 = uy * k;
        const z2 = uz * k;
        const s = persp / (persp - z2);
        const depth = (z2 + 1.2) / 2.4;
        const size = dot * (0.45 + depth * 1.1) * s;
        const img = depth > 0.55 ? (callerMix > 0.5 && depth > 0.7 ? whiteSprite : skySprite) : blueSprite;
        ctx.globalAlpha = Math.min(1, 0.08 + depth * depth * 0.95);
        ctx.drawImage(img, cx + x1 * R * s - size, cy + y2 * R * s - size, size * 2, size * 2);
      }
      ctx.globalAlpha = 1;
      ctx.globalCompositeOperation = "source-over";
    };

    if (reduce) {
      draw(16);
      return () => ro.disconnect();
    }

    let raf = 0;
    let last = performance.now();
    let acc = 0;
    let visible = true;
    const loop = (now: number) => {
      raf = requestAnimationFrame(loop);
      const dt = Math.min(64, now - last);
      last = now;
      if (!visible) return;
      acc += dt;
      if (acc < frameMs - 1) return;
      draw(acc);
      acc = 0;
    };
    raf = requestAnimationFrame(loop);
    const io = new IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting;
    });
    io.observe(canvas);

    return () => {
      cancelAnimationFrame(raf);
      io.disconnect();
      ro.disconnect();
      window.removeEventListener("pointermove", onPointer);
    };
  }, [signal]);

  return <canvas ref={canvasRef} className={className} aria-hidden="true" />;
}
