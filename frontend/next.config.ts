import type { NextConfig } from "next";

// NEXT_PUBLIC_* values are inlined at build time. A production deployment built without
// them would ship a site that talks to localhost (or, over http, is blocked as mixed
// content), so the build fails instead and the host keeps serving the previous one.
if (process.env.VERCEL_ENV === "production") {
  for (const [key, scheme] of [
    ["NEXT_PUBLIC_API_URL", "https://"],
    ["NEXT_PUBLIC_WS_URL", "wss://"],
  ] as const) {
    if (!process.env[key]?.startsWith(scheme)) {
      throw new Error(`${key} must be the backend's ${scheme} URL for a production deployment`);
    }
  }
}

const nextConfig: NextConfig = {
  output: "standalone",
  reactStrictMode: true,
  poweredByHeader: false,
  typedRoutes: true,
  experimental: {
    optimizePackageImports: ["lucide-react"],
  },
  headers: async () => [
    {
      source: "/(.*)",
      headers: [
        { key: "X-Content-Type-Options", value: "nosniff" },
        { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
        { key: "X-Frame-Options", value: "DENY" },
      ],
    },
  ],
};

export default nextConfig;
