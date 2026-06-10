"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { fetchJobText, fmtTime, type ChapterInfo } from "@/lib/api";
import {
  buildPages, charAtTime, charsPerPageFor, pageForPosition, timeAtChar,
  type BookText, type Page, type Para,
} from "@/lib/reader";

interface Props {
  jobId: string;
  chapters: ChapterInfo[]; // audio chapter starts (seconds)
  time: number;            // current audio time
  duration: number;        // total audio duration
  onSeek: (t: number) => void;
}

type LoadState =
  | { kind: "loading" }
  | { kind: "building"; progress: number; message: string }
  | { kind: "error"; message: string }
  | { kind: "ready"; book: BookText };

export function ReadAlong({ jobId, chapters, time, duration, onSeek }: Props) {
  const [load, setLoad] = useState<LoadState>({ kind: "loading" });
  const [attempt, setAttempt] = useState(0); // bump to refetch after an error
  const [pageIdx, setPageIdx] = useState(0);
  const [following, setFollowing] = useState(true);
  const [charsPerPage, setCharsPerPage] = useState(900);
  // While following, a crossed illustration page is shown briefly before
  // the reader settles on the live text page — like glancing at the art
  // while the narration carries on.
  const [interlude, setInterlude] = useState<number | null>(null);
  const prevLivePage = useRef<number | null>(null);
  const pageRef = useRef<HTMLDivElement>(null);

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

  // ---- measure the page box -> chars per page -------------------------
  useEffect(() => {
    function measure() {
      const el = pageRef.current;
      if (!el) return;
      const rect = el.getBoundingClientRect();
      if (rect.width > 0 && rect.height > 0) {
        setCharsPerPage(charsPerPageFor(rect.width, rect.height));
      }
    }
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, [load.kind]);

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

  // Auto page-turn while following.
  useEffect(() => {
    if (following && live && live.page !== pageIdx) setPageIdx(live.page);
  }, [following, live, pageIdx]);

  // Art interlude: when the live page steps forward past an illustration,
  // show it for a few seconds. Only for small steps (reading flow), not
  // big seeks.
  useEffect(() => {
    if (!following || !live) return;
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
  }, [live, following, pages]);

  // Clamp page index if repagination shrank the book.
  useEffect(() => {
    if (pages.length && pageIdx >= pages.length) setPageIdx(pages.length - 1);
  }, [pages.length, pageIdx]);

  // Functional update so rapid taps each advance a page (two clicks in
  // one render batch would otherwise both compute from the same index).
  const turnBy = useCallback((delta: number) => {
    setInterlude(null);
    setPageIdx((p) => Math.max(0, Math.min(p + delta, pages.length - 1)));
    setFollowing(false);
  }, [pages.length]);

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

  const shownIdx = interlude ?? pageIdx;
  const page = pages[shownIdx];
  const book = load.book;
  if (!page) {
    return <div className="reader-panel"><p className="empty-note" style={{ padding: 18 }}>No text in this book.</p></div>;
  }

  const chTitle = book.chapters[page.chapter]?.title ?? "";
  const showResume = !following && live !== null;

  function seekToSentence(start: number) {
    if (load.kind !== "ready" || !live || page.kind !== "text") return;
    const ci = page.chapter;
    const chStart = chapters[ci]?.start ?? 0;
    const chEnd = ci + 1 < chapters.length ? chapters[ci + 1].start : duration;
    const text = book.chapters[ci]?.text ?? "";
    const marks = book.timing?.[ci] ?? null;
    onSeek(chStart + timeAtChar(text, marks, start, Math.max(0.01, chEnd - chStart)));
    setFollowing(true);
  }

  function renderPara(para: Para, pi: number) {
    const liveHere = live !== null && page.chapter === live.ci && shownIdx === live.page;
    return (
      <p className="reader-para" key={pi}>
        {para.sentences.map((s, si) => {
          const isLive = liveHere && live!.char >= s.start && live!.char < s.start + s.text.length;
          const label = si === 0 && para.speakerLen ? s.text.slice(0, para.speakerLen) : null;
          const body = label ? s.text.slice(para.speakerLen) : s.text;
          return (
            <span
              key={s.start}
              className={`reader-sentence${isLive ? " live" : ""}`}
              onClick={() => seekToSentence(s.start)}
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

  return (
    <div className="reader-panel">
      <div className="reader-topbar">
        <span className="reader-chapter" title={chTitle}>{chTitle}</span>
        <span className="reader-pageno">{shownIdx + 1} / {pages.length}</span>
      </div>

      {page.kind === "image" ? (
        <div className="reader-page reader-page-art" ref={pageRef} key={`art-${shownIdx}`}>
          <img src={`/api/job/${jobId}/page-image/${page.file}`} alt="Illustration from the book" loading="lazy" />
        </div>
      ) : (
        <div className="reader-page" ref={pageRef} key={shownIdx} aria-live="off">
          {page.paras.map(renderPara)}
        </div>
      )}

      <div className="reader-controls">
        <button type="button" className="btn-ghost" onClick={() => turnBy(-1)} disabled={shownIdx === 0} aria-label="Previous page">
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
        <button type="button" className="btn-ghost" onClick={() => turnBy(1)} disabled={shownIdx >= pages.length - 1} aria-label="Next page">
          Next
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><polyline points="9 18 15 12 9 6" /></svg>
        </button>
      </div>
    </div>
  );
}
