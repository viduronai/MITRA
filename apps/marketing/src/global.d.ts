import type Lenis from "lenis";

declare global {
  interface Window {
    /** Shared Lenis instance (absent under reduced motion). */
    __mitraLenis?: Lenis;
  }
}

export {};
