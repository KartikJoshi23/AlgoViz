"use client";

import { useEffect, useState, useSyncExternalStore, type RefObject } from "react";

const subscribeVisibility = (cb: () => void) => {
  document.addEventListener("visibilitychange", cb);
  return () => document.removeEventListener("visibilitychange", cb);
};
const getTabVisible = () => document.visibilityState !== "hidden";
const getServerVisible = () => true;

/**
 * True while the element is on screen and the tab is visible — the render
 * loops pause otherwise so an off-screen terrain costs nothing.
 */
export function useVisible(ref: RefObject<Element | null>, rootMargin = "80px"): boolean {
  const [onScreen, setOnScreen] = useState(true);
  const tabVisible = useSyncExternalStore(subscribeVisibility, getTabVisible, getServerVisible);

  useEffect(() => {
    const el = ref.current;
    if (!el || typeof IntersectionObserver === "undefined") return;
    const io = new IntersectionObserver(([e]) => setOnScreen(!!e?.isIntersecting), { rootMargin });
    io.observe(el);
    return () => io.disconnect();
  }, [ref, rootMargin]);

  return onScreen && tabVisible;
}
