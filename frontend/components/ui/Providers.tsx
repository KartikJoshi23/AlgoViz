"use client";

import { QueryClient, QueryClientProvider, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type ReactNode } from "react";

import { gsap } from "@/lib/gsap";
import { usePerfDetection } from "@/lib/perf/tier";
import { PREFS_STORAGE_KEY, useEffectiveMotion, useEffectiveTier, useStore } from "@/lib/store";
import { wsClient } from "@/lib/ws/client";
import { ALL_CHANNELS } from "@/lib/ws/types";

function Boot({ children }: { children: ReactNode }) {
  usePerfDetection();
  const prefs = useStore((s) => s.prefs);
  const motion = useEffectiveMotion();
  const tier = useEffectiveTier();

  // Dev-only: expose the store for debugging in the console.
  const qc = useQueryClient();
  useEffect(() => {
    if (process.env.NODE_ENV !== "production") {
      const w = window as unknown as { __algoviz: typeof useStore; __qc: QueryClient; __gsap: typeof gsap };
      w.__algoviz = useStore;
      w.__qc = qc;
      w.__gsap = gsap;
    }
  }, [qc]);

  // WebSocket lifecycle — one connection for the whole app.
  useEffect(() => {
    const channels = prefs.bookSubscribed ? [...ALL_CHANNELS] : ALL_CHANNELS.filter((c) => c !== "book");
    wsClient.start({ symbol: prefs.symbol, channels });
    return () => wsClient.stop();
    // start once; symbol / channel changes are pushed via setSymbol / subscribe below
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (prefs.symbol) wsClient.setSymbol(prefs.symbol);
  }, [prefs.symbol]);

  useEffect(() => {
    const channels = prefs.bookSubscribed ? [...ALL_CHANNELS] : ALL_CHANNELS.filter((c) => c !== "book");
    wsClient.subscribe(channels);
  }, [prefs.bookSubscribed]);

  // Preferences changed in another tab: rehydrate so both tabs agree.
  useEffect(() => {
    const onStorage = (e: StorageEvent) => {
      if (e.key === PREFS_STORAGE_KEY && e.newValue) void useStore.persist.rehydrate();
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  // Ambient intensity → the CSS variable that scales the background tint.
  useEffect(() => {
    document.documentElement.style.setProperty("--accent-intensity", String(prefs.accentIntensity));
  }, [prefs.accentIntensity]);

  // The effective motion preference (OS setting or in-app override) also governs CSS motion.
  useEffect(() => {
    document.documentElement.dataset.motion = motion ? "full" : "reduced";
  }, [motion]);

  // The effective GPU tier: on "low", CSS drops glass blur and looping ambient motion.
  useEffect(() => {
    document.documentElement.dataset.tier = tier;
  }, [tier]);

  return <>{children}</>;
}

export function Providers({ children }: { children: ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: { staleTime: 5_000, refetchOnWindowFocus: false, retry: 1 },
        },
      }),
  );
  return (
    <QueryClientProvider client={client}>
      <Boot>{children}</Boot>
    </QueryClientProvider>
  );
}
