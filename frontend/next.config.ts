import type { NextConfig } from "next";

// Production (`next build`): static export to frontend/out — FastAPI serves it
// on port 8765, so phone access over Tailscale needs only the one server.
// Dev (`next dev`): normal server on :3000 with API calls proxied to the
// FastAPI backend, so relative fetch() URLs work identically in both modes.
const isProd = process.env.NODE_ENV === "production";

const BACKEND = "http://127.0.0.1:8765";
const API_PATHS = ["/api/:path*", "/upload", "/voice-sample/:path*", "/stream/:path*", "/download/:path*", "/ambiance/:path*"];

const nextConfig: NextConfig = {
  ...(isProd ? { output: "export" as const, trailingSlash: true } : {}),
  images: { unoptimized: true },
  ...(isProd
    ? {}
    : {
        async rewrites() {
          return API_PATHS.map((p) => ({ source: p, destination: `${BACKEND}${p}` }));
        },
      }),
};

export default nextConfig;
