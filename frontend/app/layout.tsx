import type { Metadata, Viewport } from "next";
import { GeistMono } from "geist/font/mono";
import { GeistSans } from "geist/font/sans";
import type { ReactNode } from "react";

import { AmbientLayer } from "@/components/ui/AmbientLayer";
import { AppBar } from "@/components/ui/AppBar";
import { CommandPalette } from "@/components/ui/CommandPalette";
import { ConnectionBanner } from "@/components/ui/ConnectionBanner";
import { Providers } from "@/components/ui/Providers";
import { StatusBar } from "@/components/ui/StatusBar";
import { Toasts } from "@/components/ui/Toasts";

import "./globals.css";

export const metadata: Metadata = {
  title: { default: "AlgoViz — Depth", template: "%s · AlgoViz" },
  description:
    "Real-time market-microstructure intelligence: L2 order book, order-flow imbalance, regime detection, calibrated ML signals, backtesting.",
  applicationName: "AlgoViz",
  icons: { icon: "/icon.svg" },
};

export const viewport: Viewport = {
  themeColor: "#060911",
  colorScheme: "dark",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={`${GeistSans.variable} ${GeistMono.variable} dark`} suppressHydrationWarning>
      <body className="min-h-full antialiased">
        <Providers>
          <AmbientLayer />
          <a href="#main" className="btn sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-50">
            Skip to content
          </a>
          <AppBar />
          <ConnectionBanner />
          {/* bottom padding clears the mobile tab bar (56 px) and the desktop status bar (28 px) */}
          <main id="main" className="mx-auto w-full max-w-[1600px] px-3 pb-24 pt-4 md:px-6 md:pb-14 md:pt-5">
            {children}
          </main>
          <StatusBar />
          <CommandPalette />
          <Toasts />
        </Providers>
      </body>
    </html>
  );
}
