"use client";

import { useSyncExternalStore } from "react";

const noSubscribe = () => () => {};

/**
 * false on the server and while hydrating, true afterwards (and immediately on
 * client-side navigation). For data that can already be in hand when a
 * component hydrates — a query the app shell fetched first — so its first
 * render still matches the prerendered HTML; React re-renders right after.
 */
export function useHydrationDone(): boolean {
  return useSyncExternalStore(
    noSubscribe,
    () => true,
    () => false,
  );
}
