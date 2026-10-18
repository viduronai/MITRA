"use client";

import { useEffect, useRef, useState } from "react";

const DIGITS = "0123456789";

/**
 * Dot-matrix numeral that scrambles like a departure board, then settles on
 * its value the first time it scrolls into view. Static under reduced motion.
 */
export function DotNumber({ value, className, delay = 0 }: { value: string; className?: string; delay?: number }) {
  const ref = useRef<HTMLSpanElement>(null);
  const [shown, setShown] = useState(value);

  useEffect(() => {
    const el = ref.current;
    if (!el || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    let timer = 0;
    let start = 0;
    const tick = () => {
      const t = performance.now() - start;
      const settled = Math.floor(t / 110);
      setShown(
        value
          .split("")
          .map((ch, i) => (/\d/.test(ch) && i >= settled ? DIGITS[Math.floor(Math.random() * 10)] : ch))
          .join(""),
      );
      if (settled < value.length) timer = window.setTimeout(tick, 55);
      else setShown(value);
    };
    const io = new IntersectionObserver(
      ([e]) => {
        if (!e.isIntersecting) return;
        io.disconnect();
        timer = window.setTimeout(() => {
          start = performance.now() + 250;
          tick();
        }, delay);
      },
      { threshold: 0.6 },
    );
    io.observe(el);
    return () => {
      io.disconnect();
      clearTimeout(timer);
    };
  }, [value, delay]);

  return (
    <span ref={ref} className={className}>
      <span aria-hidden="true">{shown}</span>
      <span className="sr-only">{value}</span>
    </span>
  );
}
