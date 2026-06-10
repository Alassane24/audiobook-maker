import type { Metadata, Viewport } from "next";
import { Marcellus, Jost } from "next/font/google";
import "./globals.css";

// Self-hosted at build time by next/font — no Google Fonts request at
// runtime, which matters because this app is reached over Tailscale,
// sometimes from networks that are slow or blocked.
const marcellus = Marcellus({ weight: "400", subsets: ["latin"], variable: "--font-display" });
const jost = Jost({ weight: ["300", "400", "500", "600", "700"], subsets: ["latin"], variable: "--font-body" });

export const metadata: Metadata = {
  title: "Audiobook Maker",
  description: "Drop in an EPUB, pick a voice, and get a beautifully narrated audiobook.",
};

export const viewport: Viewport = {
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
  el.classList.remove("theme-dark", "theme-light");
  el.classList.add(t === "theme-light" ? "theme-light" : "theme-dark");
})();
`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`theme-dark ${marcellus.variable} ${jost.variable}`} suppressHydrationWarning>
      <body>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
        <div className="grain" aria-hidden="true" />
        <div className="container">{children}</div>
      </body>
    </html>
  );
}
