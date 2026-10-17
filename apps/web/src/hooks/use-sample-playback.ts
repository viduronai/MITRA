"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Simulated sample playback (no real audio yet). Only one sample plays at a
 * time; it stops by itself after `durationMs`.
 */
export function useSamplePlayback(durationMs = 4000) {
  const [playingId, setPlayingId] = useState<string | null>(null);
  const timer = useRef<number | null>(null);

  const clearTimer = useCallback(() => {
    if (timer.current !== null) window.clearTimeout(timer.current);
    timer.current = null;
  }, []);

  const toggle = useCallback(
    (id: string) => {
      clearTimer();
      if (playingId === id) {
        setPlayingId(null);
        return;
      }
      setPlayingId(id);
      timer.current = window.setTimeout(() => {
        timer.current = null;
        setPlayingId(null);
      }, durationMs);
    },
    [clearTimer, durationMs, playingId],
  );

  useEffect(() => clearTimer, [clearTimer]);

  return { playingId, toggle };
}
