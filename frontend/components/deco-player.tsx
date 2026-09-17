"use client";

import { useEffect, useRef, useState } from "react";
import { fmtTime, type ChapterInfo } from "@/lib/api";
import { BookOpenIcon, BookmarkIcon, ExpandIcon, ListIcon, PauseIcon, PlayIcon, Skip15Back, Skip15Fwd, TrashIcon } from "./icons";
import { Sunburst } from "./sunburst";
import { ReadAlong } from "./read-along";

interface Props {
  jobId: string;
  chapters: ChapterInfo[];
}

type Bookmark = { time: number; label: string };

export function DecoPlayer({ jobId, chapters }: Props) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const [playing, setPlaying] = useState(false);
  const [time, setTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [view, setView] = useState<"chapters" | "bookmarks" | "reader">("chapters");
  const [immersive, setImmersive] = useState(false);

  const [savedTime, setSavedTime] = useState<number | null>(null);
  const [bookmarks, setBookmarks] = useState<Bookmark[]>([]);

  // Load progress and bookmarks on mount
  useEffect(() => {
    try {
      const bmarks = localStorage.getItem(`ab_bookmarks_${jobId}`);
      if (bmarks) setBookmarks(JSON.parse(bmarks));
      const prog = localStorage.getItem(`ab_progress_${jobId}`);
      if (prog) {
        const t = parseFloat(prog);
        // Only prompt to resume if they are at least 15 seconds in, to avoid annoying prompts
        if (t > 15) {
          setSavedTime(t);
        }
      }
    } catch (e) {}
  }, [jobId]);

  // Save progress periodically as time updates
  useEffect(() => {
    if (time > 0) {
      localStorage.setItem(`ab_progress_${jobId}`, time.toString());
    }
  }, [time, jobId]);

  // Active chapter follows the playhead: the last chapter whose start
  // we've passed. -1 before metadata loads.
  let active = -1;
  for (let i = 0; i < chapters.length; i++) {
    if (time >= chapters[i].start - 0.25) active = i;
    else break;
  }

  useEffect(() => {
    if (view !== "chapters" || active < 0 || !listRef.current) return;
    const row = listRef.current.children[active] as HTMLElement | undefined;
    if (!row) return;
    const smooth = !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    row.scrollIntoView({ block: "nearest", behavior: smooth ? "smooth" : "auto" });
  }, [active, view]);

  function toggle() {
    const a = audioRef.current;
    if (!a) return;
    if (a.paused) a.play();
    else a.pause();
  }

  function skip(amount: number) {
    const a = audioRef.current;
    if (a) a.currentTime = Math.max(0, a.currentTime + amount);
  }

  function seekTo(seconds: number) {
    const a = audioRef.current;
    if (!a) return;
    a.currentTime = seconds;
    a.play().catch(()=>{});
  }

  // Scrub without forcing playback (the dock/scrub bar just repositions).
  function scrubTo(seconds: number) {
    const a = audioRef.current;
    if (a) a.currentTime = seconds;
  }

  function resumeFromSave() {
    if (savedTime !== null) {
      seekTo(savedTime);
      setSavedTime(null);
    }
  }

  function dismissResume() {
    setSavedTime(null);
    // Overwrite with 0 so it doesn't prompt again if they refresh without playing
    localStorage.setItem(`ab_progress_${jobId}`, "0");
  }

  function addBookmark() {
    const label = window.prompt("Enter a name or note for this bookmark:", `Bookmark at ${fmtTime(time)}`);
    if (!label) return; // user cancelled or empty
    const newBm = [...bookmarks, { time, label }];
    newBm.sort((a, b) => a.time - b.time);
    setBookmarks(newBm);
    localStorage.setItem(`ab_bookmarks_${jobId}`, JSON.stringify(newBm));
    setView("bookmarks"); // jump to bookmarks view to show it
  }

  function deleteBookmark(idx: number, e: React.MouseEvent) {
    e.stopPropagation();
    const newBm = [...bookmarks];
    newBm.splice(idx, 1);
    setBookmarks(newBm);
    localStorage.setItem(`ab_bookmarks_${jobId}`, JSON.stringify(newBm));
  }

  // Did our request actually put the browser into fullscreen? Only then does
  // leaving fullscreen (Esc) mean "close the reader" — otherwise a browser
  // that denies or instantly drops fullscreen would collapse the overlay.
  const enteredFsRef = useRef(false);

  // Full-screen reading mode. Switch to the reader, request the browser's
  // fullscreen (so a Chrome app window goes borderless), and flip into the
  // immersive overlay. The overlay is CSS-driven and fills the window on its
  // own, so it works even if fullscreen is blocked.
  function enterImmersive() {
    setView("reader");
    setImmersive(true);
    const p = document.documentElement.requestFullscreen?.();
    if (p && typeof p.then === "function") {
      p.then(() => { enteredFsRef.current = true; }).catch(() => { enteredFsRef.current = false; });
    }
  }

  function exitImmersive() {
    enteredFsRef.current = false;
    setImmersive(false);
    if (document.fullscreenElement) document.exitFullscreen?.().catch(() => {});
  }

  // Esc leaves browser fullscreen on its own — close the overlay to match,
  // but only if we were the ones who entered fullscreen.
  useEffect(() => {
    function onFsChange() {
      if (!document.fullscreenElement && enteredFsRef.current) {
        enteredFsRef.current = false;
        setImmersive(false);
      }
    }
    document.addEventListener("fullscreenchange", onFsChange);
    return () => document.removeEventListener("fullscreenchange", onFsChange);
  }, []);

  const scrubFill = duration > 0 ? (time / duration) * 100 : 0;

  return (
    <div>
      {/* /stream (not /download): inline disposition + range support,
          required for iOS Safari to actually play it. */}
      <audio
        ref={audioRef}
        src={`/stream/${jobId}`}
        preload="metadata"
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
        onTimeUpdate={(e) => setTime(e.currentTarget.currentTime)}
        onLoadedMetadata={(e) => setDuration(e.currentTarget.duration)}
        onEnded={() => setPlaying(false)}
      />

      {savedTime !== null && (
        <div className="banner" style={{ display: "flex", justifyContent: "space-between", marginBottom: 20 }}>
          <span>Resume where you left off ({fmtTime(savedTime)})?</span>
          <div style={{ display: "flex", gap: 8 }}>
            <button type="button" className="btn-ghost" onClick={resumeFromSave}>Resume</button>
            <button type="button" className="btn-ghost" onClick={dismissResume}>Dismiss</button>
          </div>
        </div>
      )}

      <div className="player-shell">
        <div className="transport">
          <button type="button" className="skip-btn" onClick={() => skip(-15)} aria-label="Back 15 seconds">
            <Skip15Back />
          </button>
          <div className="sunburst-wrap">
            <Sunburst />
            <button type="button" className={`roundel roundel-xl${playing ? " playing" : ""}`} onClick={toggle} aria-label={playing ? "Pause" : "Play"}>
              {playing ? <PauseIcon /> : <PlayIcon style={{ marginLeft: 4 }} />}
            </button>
          </div>
          <button type="button" className="skip-btn" onClick={() => skip(15)} aria-label="Forward 15 seconds">
            <Skip15Fwd />
          </button>
        </div>

        <div className="scrub-row">
          <span className="time-readout left">{fmtTime(time)}</span>
          <input
            type="range"
            min={0}
            max={100}
            step={0.1}
            value={scrubFill}
            aria-label="Seek"
            style={{ "--fill": `${scrubFill}%` } as React.CSSProperties}
            onChange={(e) => {
              const a = audioRef.current;
              if (a && a.duration) a.currentTime = (parseFloat(e.target.value) / 100) * a.duration;
            }}
          />
          <span className="time-readout right">{fmtTime(duration)}</span>
        </div>

        <div className="view-toggle" role="tablist" aria-label="Player view">
          <button
            type="button"
            role="tab"
            aria-selected={view === "chapters"}
            className={`view-tab${view === "chapters" ? " sel" : ""}`}
            onClick={() => setView("chapters")}
          >
            <ListIcon /> Chapters
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={view === "bookmarks"}
            className={`view-tab${view === "bookmarks" ? " sel" : ""}`}
            onClick={() => setView("bookmarks")}
          >
            <BookmarkIcon /> Bookmarks
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={view === "reader"}
            className={`view-tab${view === "reader" ? " sel" : ""}`}
            onClick={() => setView("reader")}
          >
            <BookOpenIcon /> Read along
          </button>
          <button
            type="button"
            className="view-tab fs-entry"
            onClick={enterImmersive}
            aria-label="Open the full-screen reader"
          >
            <ExpandIcon /> Full screen
          </button>
        </div>
        
        {/* Bookmark Action Button within player shell */}
        <div style={{ display: "flex", justifyContent: "center", marginTop: 16 }}>
          <button type="button" className="btn-ghost" onClick={addBookmark}>
            <BookmarkIcon /> Bookmark this moment
          </button>
        </div>
      </div>

      {view === "reader" ? (
        <ReadAlong
          jobId={jobId}
          chapters={chapters}
          time={time}
          duration={duration}
          onSeek={seekTo}
          immersive={immersive}
          onEnterImmersive={enterImmersive}
          onExitImmersive={exitImmersive}
          playing={playing}
          onTogglePlay={toggle}
          onSkip={skip}
          onScrub={scrubTo}
        />
      ) : view === "bookmarks" ? (
        <div className="ch-list" role="list" aria-label="Bookmarks">
          {bookmarks.length > 0 ? (
            bookmarks.map((bm, i) => (
              <div
                key={i}
                role="listitem"
                className="ch-row"
                onClick={() => seekTo(bm.time)}
                style={{ justifyContent: "space-between" }}
              >
                <div style={{ display: "flex", gap: 16, alignItems: "baseline" }}>
                  <span className="ch-time">{fmtTime(bm.time)}</span>
                  <span className="ch-title">{bm.label}</span>
                </div>
                <button
                  type="button"
                  className="btn-ghost danger"
                  onClick={(e) => deleteBookmark(i, e)}
                  aria-label="Delete bookmark"
                  style={{ minHeight: "auto", padding: "6px 10px" }}
                >
                  <TrashIcon />
                </button>
              </div>
            ))
          ) : (
            <p className="empty-note" style={{ padding: 18, textAlign: "center" }}>No bookmarks yet.</p>
          )}
        </div>
      ) : (
        chapters.length > 0 && (
          <div className="ch-list" ref={listRef} role="list" aria-label="Chapters">
            {chapters.map((ch, i) => (
              <button
                key={i}
                type="button"
                role="listitem"
                className={`ch-row${i === active ? " active" : ""}`}
                onClick={() => seekTo(ch.start)}
                aria-label={`Play ${ch.title} from ${fmtTime(ch.start)}`}
              >
                <span className="ch-time">{fmtTime(ch.start)}</span>
                <span className="ch-title">{ch.title}</span>
              </button>
            ))}
          </div>
        )
      )}
    </div>
  );
}
