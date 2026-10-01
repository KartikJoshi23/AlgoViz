"use client";

import { useCallback, useSyncExternalStore } from "react";

/**
 * A clock that re-renders every `intervalMs`. Built on useSyncExternalStore
 * (no setState-in-effect); the snapshot is quantised to the interval so
 * consecutive reads within one tick are stable.
 */
export function useNow(intervalMs = 1000, active = true): number {
  const subscribe = useCallback(
    (onChange: () => void) => {
      if (!active) return () => {};
      const id = setInterval(onChange, intervalMs);
      return () => clearInterval(id);
    },
    [intervalMs, active],
  );
  const get = useCallback(() => (active ? Math.floor(Date.now() / intervalMs) * intervalMs : 0), [intervalMs, active]);
  return useSyncExternalStore(subscribe, get, () => 0);
}
