"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { BrandIcon, MoonIcon, MoonStarIcon, SunIcon } from "./icons";

type Theme = "theme-dark" | "theme-light" | "theme-night";

// Cycle order goes darker each tap, then back around to light.
const NEXT: Record<Theme, Theme> = {
  "theme-light": "theme-dark",
  "theme-dark": "theme-night",
  "theme-night": "theme-light",
};

const NEXT_LABEL: Record<Theme, string> = {
  "theme-light": "Switch to dark theme",
  "theme-dark": "Switch to night theme (true black)",
  "theme-night": "Switch to light theme",
};

// The button shows the theme you'll GET by pressing it.
function nextIcon(theme: Theme) {
  switch (NEXT[theme]) {
    case "theme-light": return <SunIcon />;
    case "theme-dark": return <MoonIcon />;
    case "theme-night": return <MoonStarIcon />;
  }
}

function currentTheme(): Theme {
  if (typeof document === "undefined") return "theme-dark";
  const cl = document.documentElement.classList;
  if (cl.contains("theme-light")) return "theme-light";
  if (cl.contains("theme-night")) return "theme-night";
  return "theme-dark";
}

export function HeaderBar() {
  // Theme lives on <html> (set pre-paint by the layout script); this
  // state only drives which toggle icon shows, so sync it after mount.
  const [theme, setTheme] = useState<Theme>("theme-dark");
  useEffect(() => setTheme(currentTheme()), []);

  function cycle() {
    const next = NEXT[theme];
    const el = document.documentElement;
    el.classList.remove("theme-dark", "theme-light", "theme-night");
    el.classList.add(next);
    localStorage.setItem("theme", next);
    setTheme(next);
  }

  return (
    <header className="masthead">
      <Link href="/" className="brand reveal" aria-label="Audiobook Maker — back to home">
        <span className="brand-icon reveal-icon">
          <BrandIcon />
        </span>
        <h1>Audiobook Maker</h1>
      </Link>
      <button
        type="button"
        className="theme-btn"
        onClick={cycle}
        aria-label={NEXT_LABEL[theme]}
        title={NEXT_LABEL[theme]}
      >
        {nextIcon(theme)}
      </button>
    </header>
  );
}
