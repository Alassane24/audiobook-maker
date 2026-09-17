import type { Metadata, Viewport } from "next";
import { Marcellus, Jost, Newsreader } from "next/font/google";
import "./globals.css";

// Self-hosted at build time by next/font — no Google Fonts request at
// runtime, which matters because this app is reached over Tailscale,
// sometimes from networks that are slow or blocked.
const marcellus = Marcellus({ weight: "400", subsets: ["latin"], variable: "--font-display" });
const jost = Jost({ weight: ["300", "400", "500", "600", "700"], subsets: ["latin"], variable: "--font-body" });
// The read-along page is long-form book text; it gets a real text serif.
const newsreader = Newsreader({ weight: ["400", "500"], subsets: ["latin"], variable: "--font-reader" });

// PWA install metadata. Static icon/manifest files (in public/, copied to
// out/ at build) with explicit root-absolute hrefs — the clean path that a
// plain static server (our FastAPI StaticFiles) serves without query-string
// or route quirks. On iOS the apple-touch-icon is what actually shows on the
// home screen; the manifest covers Android/Chrome. "Audire" is the launcher
// name (apple-mobile-web-app-title + manifest short_name).
export const metadata: Metadata = {
  applicationName: "Audire",
  title: "Audire — Audiobook Maker",
  description: "Drop in an EPUB, pick a voice, and get a beautifully narrated audiobook.",
  manifest: "/manifest.webmanifest",
  icons: {
    icon: [
      { url: "/favicon.ico", sizes: "any" },
      { url: "/icon-192.png", type: "image/png", sizes: "192x192" },
      { url: "/icon-512.png", type: "image/png", sizes: "512x512" },
    ],
    apple: [{ url: "/apple-touch-icon.png", sizes: "180x180", type: "image/png" }],
  },
  appleWebApp: { capable: true, title: "Audire", statusBarStyle: "black-translucent" },
  // Next 15 emits the modern mobile-web-app-capable from appleWebApp.capable;
  // older iOS Safari still needs the legacy apple- name to launch standalone.
  other: { "apple-mobile-web-app-capable": "yes" },
};

export const viewport: Viewport = {
  // cover = draw under the status bar/notch; paired with safe-area padding in
  // globals.css so the masthead never hides behind the clock in standalone.
  viewportFit: "cover",
  themeColor: [
    { media: "(prefers-color-scheme: dark)", color: "#0d1f17" },
    { media: "(prefers-color-scheme: light)", color: "#efe6cd" },
  ],
};

// Runs before first paint so the saved theme never flashes. Keeps the
// legacy localStorage key/values from the old inline UI; the retired
// neon themes (midnight/crimson/matcha) collapse to dark. classList
// surgery only — a whole-className assignment would strip the next/font
// variable classes off <html> and take the custom fonts down with them.
const themeScript = `
(function () {
  var t = localStorage.getItem("theme");
  var el = document.documentElement;
  el.classList.remove("theme-dark", "theme-light", "theme-night");
  el.classList.add(t === "theme-light" || t === "theme-night" ? t : "theme-dark");
})();
`;

// Marks the page as running on a landscape MONITOR (not the window shape) so
// the wide desktop layout keys off the real screen. A Chrome app window that
// is taller than it is wide would report orientation:portrait to CSS — using
// the screen instead means a desktop app window still gets the desktop layout,
// while a phone or a vertical/portrait monitor keeps the narrow column. Runs
// pre-paint and re-checks when the window moves between monitors.
const screenScript = `
(function () {
  function set() {
    try {
      var s = window.screen || {};
      document.documentElement.classList.toggle("landscape-screen", (s.width || 0) >= (s.height || 0));
    } catch (e) {}
  }
  set();
  window.addEventListener("resize", set);
  window.addEventListener("orientationchange", set);
})();
`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`theme-dark ${marcellus.variable} ${jost.variable} ${newsreader.variable}`} suppressHydrationWarning>
      <body>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
        <script dangerouslySetInnerHTML={{ __html: screenScript }} />
        <div className="grain" aria-hidden="true" />
        <div className="container">{children}</div>
      </body>
    </html>
  );
}
