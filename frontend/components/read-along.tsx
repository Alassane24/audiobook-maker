"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { fetchJobText, fmtTime, type ChapterInfo } from "@/lib/api";
import {
  buildPages, charAtTime, charsPerPageFor, pageForPosition, timeAtChar,
  type BookText, type Page, type Para,
} from "@/lib/reader";
import {
  ExpandIcon, MinimizeIcon, PauseIcon, PlayIcon, Skip15Back, Skip15Fwd,
} from "./icons";

interface Props {
  jobId: string;
  chapters: ChapterInfo[]; // audio chapter starts (seconds)
  time: number;            // current audio time
  duration: number;        // total audio duration
  onSeek: (t: number) => void;     // play from a position (sentence tap)
  immersive: boolean;
  onEnterImmersive: () => void;
  onExitImmersive: () => void;
  playing: boolean;
  onTogglePlay: () => void;
  onSkip: (sec: number) => void;
  onScrub: (t: number) => void;    // set position without forcing play
}

type LoadState =
  | { kind: "loading" }
  | { kind: "building"; progress: number; message: string }
  | { kind: "error"; message: string }
  | { kind: "ready"; book: BookText };

// Below this stage width the reader stays single-page; above it, two pages
// sit side by side. Hysteresis (768 to enter, 700 to leave) stops a column
// flip-flopping when the window hovers around the threshold.
const TWO_UP_ENTER = 768;
const TWO_UP_LEAVE = 700;

export function ReadAlong({
  jobId, chapters, time, duration, onSeek,
  immersive, onEnterImmersive, onExitImmersive,
  playing, onTogglePlay, onSkip, onScrub,
}: Props) {
  const [load, setLoad] = useState<LoadState>({ kind: "loading" });
  const [attempt, setAttempt] = useState(0); // bump to refetch after an error
  const [pageIdx, setPageIdx] = useState(0);
  const [following, setFollowing] = useState(true);
  const [charsPerPage, setCharsPerPage] = useState(900);
  const [cols, setCols] = useState<1 | 2>(1);
  // While following in single-page mode, a crossed illustration page is
  // shown briefly before the reader settles on the live text page — like
  // glancing at the art while the narration carries on. (Two-up already
  // shows the art in the spread, so no interlude there.)
  const [interlude, setInterlude] = useState<number | null>(null);
  const prevLivePage = useRef<number | null>(null);
  const pageRef = useRef<HTMLDivElement>(null);  // the left page — measured
  const stageRef = useRef<HTMLDivElement>(null); // spread wrapper — sets cols

  // ---- fetch text (with 202 rebuild polling) --------------------------
  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    async function tick() {
      try {
        const r = await fetchJobText(jobId);
        if (!alive) return;
        if (r.chapters) {
          setLoad({ kind: "ready", book: { chapters: r.chapters, timing: r.timing ?? null } });
          return;
        }
        setLoad({ kind: "building", progress: r.progress ?? 0, message: r.message ?? "" });
        timer = setTimeout(tick, 2500);
      } catch (e) {
        if (alive) setLoad({ kind: "error", message: e instanceof Error ? e.message : String(e) });
      }
    }
    tick();
    return () => { alive = false; clearTimeout(timer); };
  }, [jobId, attempt]);

  // ---- measure: stage width -> columns, page box + type -> chars ------
  useEffect(() => {
    function measure() {
      const stage = stageRef.current;
      if (stage) {
        const w = stage.getBoundingClientRect().width;
        // Facing pages only make sense on a landscape MONITOR — keyed off
        // the screen, not the window, so a tall app window on a wide desktop
        // still gets two pages, while a phone or a vertical monitor (portrait
        // screen) stays a single vertical page even in full-screen.
        const sc = window.screen;
        const landscape = !sc || (sc.width || 0) >= (sc.height || 0);
        const wide = (cols: 1 | 2) => (cols === 2 ? w >= TWO_UP_LEAVE : w >= TWO_UP_ENTER);
        // functional update reads the live value, so this never loops
        setCols((prev) => (landscape && wide(prev) ? 2 : 1));
      }
      const el = pageRef.current;
      if (el) {
        const rect = el.getBoundingClientRect();
        const cs = getComputedStyle(el);
        const fontPx = parseFloat(cs.fontSize) || 17;
        const lineH = parseFloat(cs.lineHeight) || fontPx * 1.75;
        if (rect.width > 0 && rect.height > 0) {
          setCharsPerPage(charsPerPageFor(rect.width, rect.height, fontPx, lineH));
        }
      }
    }
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, [load.kind, immersive, cols]);

  // ---- pagination ------------------------------------------------------
  const pages: Page[] = useMemo(() => {
    if (load.kind !== "ready") return [];
    return buildPages(load.book.chapters, charsPerPage);
  }, [load, charsPerPage]);

  // ---- audio position -> chapter + char + live page -------------------
  const live = useMemo(() => {
    if (load.kind !== "ready" || pages.length === 0 || duration <= 0) return null;
    const book = load.book;
    const n = Math.min(chapters.length, book.chapters.length) || 1;
    let ci = 0;
    for (let i = 0; i < n; i++) if (time >= (chapters[i]?.start ?? 0) - 0.25) ci = i;
    const chStart = chapters[ci]?.start ?? 0;
    const chEnd = ci + 1 < chapters.length ? chapters[ci + 1].start : duration;
    const chDur = Math.max(0.01, chEnd - chStart);
    const text = book.chapters[ci]?.text ?? "";
    const marks = book.timing?.[ci] ?? null;
    const char = charAtTime(text, marks, time - chStart, chDur);
    return { ci, chStart, chDur, char, page: pageForPosition(pages, ci, char) };
  }, [load, pages, chapters, time, duration]);

  // Auto page-turn while following: only move when the live page leaves the
  // visible spread, so the narration can cross the left page onto the right
  // before the book turns.
  useEffect(() => {
    if (!following || !live) return;
    const within = live.page >= pageIdx && live.page <= pageIdx + cols - 1;
    if (!within) setPageIdx(live.page);
  }, [following, live, pageIdx, cols]);

  // Art interlude (single-page only): when the live page steps forward past
  // an illustration, show it for a few seconds. Only for small steps
  // (reading flow), not big seeks.
  useEffect(() => {
    if (!following || !live || cols !== 1) return;
    const prev = prevLivePage.current;
    prevLivePage.current = live.page;
    if (prev === null || live.page === prev) return;
    if (live.page > prev && live.page - prev <= 3) {
      let found: number | null = null;
      for (let i = prev + 1; i < live.page; i++) {
        if (pages[i]?.kind === "image") { found = i; break; }
      }
      if (found !== null) {
        setInterlude(found);
        const t = setTimeout(() => setInterlude(null), 4500);
        return () => clearTimeout(t);
      }
    }
  }, [live, following, pages, cols]);

  // Clamp page index if repagination shrank the book.
  useEffect(() => {
    if (pages.length && pageIdx >= pages.length) setPageIdx(pages.length - 1);
  }, [pages.length, pageIdx]);

  // Turn by a whole spread (one page, or two in two-up). Functional update
  // so rapid taps each advance — two clicks in one render batch would
  // otherwise both compute from the same index.
  const turnBy = useCallback((dir: number) => {
    setInterlude(null);
    setPageIdx((p) => Math.max(0, Math.min(p + dir * cols, pages.length - 1)));
    setFollowing(false);
  }, [pages.length, cols]);

  const resume = useCallback(() => {
    setInterlude(null);
    setFollowing(true);
    if (live) setPageIdx(live.page);
  }, [live]);

  // Keyboard page turns while the reader is on screen.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      if (e.key === "ArrowLeft") { e.preventDefault(); turnBy(-1); }
      if (e.key === "ArrowRight") { e.preventDefault(); turnBy(1); }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [turnBy]);

  // ---- non-ready states ------------------------------------------------
  if (load.kind === "loading") {
    return <div className="reader-panel"><p className="empty-note" style={{ padding: 18 }}>Opening the book…</p></div>;
  }
  if (load.kind === "building") {
    const pct = Math.round(load.progress * 100);
    return (
      <div className="reader-panel" style={{ padding: 22 }}>
        <p className="empty-note" style={{ marginTop: 0 }}>
          Preparing the text for read-along — a one-time step for books made before this feature.
        </p>
        <div className="progress-shell"><div className="progress-fill live" style={{ width: `${pct}%` }} /></div>
        <p className="job-sub" style={{ marginTop: 8 }}>{load.message || "Working…"} · {pct}%</p>
      </div>
    );
  }
  if (load.kind === "error") {
    return (
      <div className="reader-panel" style={{ padding: 16 }}>
        <p className="banner err" style={{ margin: 0 }} role="alert">{load.message}</p>
        <button
          type="button"
          className="btn-ghost"
          style={{ marginTop: 12 }}
          onClick={() => { setLoad({ kind: "loading" }); setAttempt((a) => a + 1); }}
        >
          Try again
        </button>
      </div>
    );
  }

  const book = load.book;
  // In single-page mode an art interlude can momentarily replace the live
  // page; two-up always shows the real left page.
  const leftIdx = cols === 1 ? (interlude ?? pageIdx) : pageIdx;
  const rightIdx = cols === 2 ? leftIdx + 1 : -1;
  const leftPage = pages[leftIdx];
  if (!leftPage) {
    return <div className="reader-panel"><p className="empty-note" style={{ padding: 18 }}>No text in this book.</p></div>;
  }

  const chTitle = book.chapters[leftPage.chapter]?.title ?? "";
  const showResume = !following && live !== null;
  const atStart = leftIdx <= 0;
  const atEnd = leftIdx + cols >= pages.length;
  const pageLabel = (() => {
    if (cols === 2 && rightIdx >= 0 && rightIdx < pages.length) {
      return `${leftIdx + 1}–${rightIdx + 1} / ${pages.length}`;
    }
    return `${leftIdx + 1} / ${pages.length}`;
  })();

  function seekToSentence(start: number, pg: Page) {
    if (load.kind !== "ready" || pg.kind !== "text") return;
    const ci = pg.chapter;
    const chStart = chapters[ci]?.start ?? 0;
    const chEnd = ci + 1 < chapters.length ? chapters[ci + 1].start : duration;
    const text = book.chapters[ci]?.text ?? "";
    const marks = book.timing?.[ci] ?? null;
    onSeek(chStart + timeAtChar(text, marks, start, Math.max(0.01, chEnd - chStart)));
    setFollowing(true);
  }

  function renderPara(para: Para, pi: number, pg: Page, pgIdx: number) {
    const liveHere = live !== null && pgIdx === live.page;
    return (
      <p className="reader-para" key={pi}>
        {para.sentences.map((s) => {
          const isLive = liveHere && live!.char >= s.start && live!.char < s.start + s.text.length;
          const label = para.speakerLen && para.sentences[0] === s ? s.text.slice(0, para.speakerLen) : null;
          const body = label ? s.text.slice(para.speakerLen) : s.text;
          return (
            <span
              key={s.start}
              className={`reader-sentence${isLive ? " live" : ""}`}
              onClick={() => seekToSentence(s.start, pg)}
              title="Play from here"
            >
              {label && <span className="reader-speaker">{label}</span>}
              {body}
            </span>
          );
        })}
      </p>
    );
  }

  // Render one page of the spread. `measured` attaches the sizing ref.
  function renderPage(idx: number, measured: boolean, side: "left" | "right") {
    const pg = pages[idx];
    const cls = `reader-page${side === "left" ? " left" : " right"}`;
    if (!pg) {
      // Trailing blank when an odd page count leaves the right side empty.
      return <div className={`${cls} reader-page-blank`} ref={measured ? pageRef : undefined} aria-hidden="true" />;
    }
    if (pg.kind === "image") {
      return (
        <div className={`${cls} reader-page-art`} ref={measured ? pageRef : undefined} key={`art-${idx}`}>
          <img src={`/api/job/${jobId}/page-image/${pg.file}`} alt="Illustration from the book" loading="lazy" />
        </div>
      );
    }
    return (
      <div className={cls} ref={measured ? pageRef : undefined} key={idx} aria-live="off">
        {pg.paras.map((para, pi) => renderPara(para, pi, pg, idx))}
      </div>
    );
  }

  const spread = (
    <div className={`reader-spread${cols === 2 ? " two" : ""}`} ref={stageRef}>
      {renderPage(leftIdx, true, "left")}
      {cols === 2 && renderPage(rightIdx, false, "right")}
    </div>
  );

  const scrubPct = duration > 0 ? (time / duration) * 100 : 0;

  // Audio transport reused in the immersive dock.
  const transport = (
    <div className="immersive-transport">
      <button type="button" className="btn-ghost page-arrow" onClick={() => turnBy(-1)} disabled={atStart} aria-label="Previous page">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><polyline points="15 18 9 12 15 6" /></svg>
      </button>
      <button type="button" className="skip-btn" onClick={() => onSkip(-15)} aria-label="Back 15 seconds"><Skip15Back /></button>
      <button type="button" className={`roundel roundel-xl${playing ? " playing" : ""}`} onClick={onTogglePlay} aria-label={playing ? "Pause" : "Play"}>
        {playing ? <PauseIcon /> : <PlayIcon style={{ marginLeft: 4 }} />}
      </button>
      <button type="button" className="skip-btn" onClick={() => onSkip(15)} aria-label="Forward 15 seconds"><Skip15Fwd /></button>
      <button type="button" className="btn-ghost page-arrow" onClick={() => turnBy(1)} disabled={atEnd} aria-label="Next page">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><polyline points="9 18 15 12 9 6" /></svg>
      </button>
    </div>
  );

  const scrubRow = (
    <div className="scrub-row">
      <span className="time-readout left">{fmtTime(time)}</span>
      <input
        type="range" min={0} max={100} step={0.1} value={scrubPct} aria-label="Seek"
        style={{ "--fill": `${scrubPct}%` } as React.CSSProperties}
        onChange={(e) => onScrub((parseFloat(e.target.value) / 100) * duration)}
      />
      <span className="time-readout right">{fmtTime(duration)}</span>
    </div>
  );

  // ---- immersive full-screen layout -----------------------------------
  // Portalled to <body> so the fixed overlay fills the viewport — the
  // player sits inside a card whose entrance animation leaves a lingering
  // transform, which would otherwise trap a position:fixed child.
  if (immersive && typeof document !== "undefined") {
    return createPortal(
      <div className="immersive" role="region" aria-label="Full-screen reader">
        <div className="immersive-top">
          <span className="reader-chapter" title={chTitle}>{chTitle}</span>
          <div className="immersive-top-right">
            <span className="reader-pageno">{pageLabel}</span>
            {showResume && (
              <button type="button" className="reader-resume" onClick={resume}>
                Return to narration · {fmtTime(time)}
              </button>
            )}
            <button type="button" className="btn-ghost" onClick={onExitImmersive} aria-label="Exit full screen">
              <MinimizeIcon /> Exit
            </button>
          </div>
        </div>

        <div className="immersive-stage">{spread}</div>

        <div className="immersive-dock">
          {scrubRow}
          {transport}
        </div>
      </div>,
      document.body,
    );
  }

  // ---- inline panel ----------------------------------------------------
  return (
    <div className="reader-panel">
      <div className="reader-topbar">
        <span className="reader-chapter" title={chTitle}>{chTitle}</span>
        <div className="reader-topbar-right">
          <span className="reader-pageno">{pageLabel}</span>
          <button type="button" className="btn-ghost reader-fs-btn" onClick={onEnterImmersive} aria-label="Full screen">
            <ExpandIcon /> Full screen
          </button>
        </div>
      </div>

      {spread}

      <div className="reader-controls">
        <button type="button" className="btn-ghost" onClick={() => turnBy(-1)} disabled={atStart} aria-label="Previous page">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><polyline points="15 18 9 12 15 6" /></svg>
          Prev
        </button>
        {showResume ? (
          <button type="button" className="reader-resume" onClick={resume}>
            Return to the narration · {fmtTime(time)}
          </button>
        ) : (
          <span className="reader-follow-note">{following ? "Following the narration" : ""}</span>
        )}
        <button type="button" className="btn-ghost" onClick={() => turnBy(1)} disabled={atEnd} aria-label="Next page">
          Next
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><polyline points="9 18 15 12 9 6" /></svg>
        </button>
      </div>
    </div>
  );
}
