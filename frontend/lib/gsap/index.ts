/**
 * GSAP setup. Import `gsap` from here so plugins are registered exactly once.
 * GSAP 3.13+ is free including all plugins (Webflow acquisition).
 */
import { gsap } from "gsap";
import { useGSAP } from "@gsap/react";

if (typeof window !== "undefined") {
  gsap.registerPlugin(useGSAP);
  gsap.defaults({ ease: "power3.out", duration: 0.6 });
}

export { gsap, useGSAP };

/** Shared eases so motion feels like one system. */
export const EASE = {
  out: "power3.out",
  inOut: "power2.inOut",
  expo: "expo.out",
  elastic: "elastic.out(1, 0.6)",
} as const;
