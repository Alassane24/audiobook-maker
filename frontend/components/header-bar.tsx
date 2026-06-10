"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { BrandIcon, MoonIcon, SunIcon } from "./icons";

function currentTheme(): "theme-dark" | "theme-light" {
  if (typeof document === "undefined") return "theme-dark";
  return document.documentElement.className.includes("theme-light") ? "theme-light" : "theme-dark";
}

export function HeaderBar() {
  // Theme lives on <html> (set pre-paint by the layout script); this
  // state only drives which toggle icon shows, so sync it after mount.
  const [theme, setTheme] = useState<"theme-dark" | "theme-light">("theme-dark");
  useEffect(() => setTheme(currentTheme()), []);

  function toggle() {
    const next = theme === "theme-dark" ? "theme-light" : "theme-dark";
    const el = document.documentElement;
    el.className = el.className.replace(/theme-(dark|light)/, next);
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
        onClick={toggle}
        aria-label={theme === "theme-dark" ? "Switch to light theme" : "Switch to dark theme"}
        title={theme === "theme-dark" ? "Switch to light theme" : "Switch to dark theme"}
      >
        {theme === "theme-dark" ? <SunIcon /> : <MoonIcon />}
      </button>
    </header>
  );
}
