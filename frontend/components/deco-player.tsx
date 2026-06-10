"use client";

import { useEffect, useRef, useState } from "react";
import { fmtTime, type ChapterInfo } from "@/lib/api";
import { PauseIcon, PlayIcon, Skip15Back, Skip15Fwd } from "./icons";
import { Sunburst } from "./sunburst";

interface Props {
  jobId: string;
  chapters: ChapterInfo[];
}

export function DecoPlayer({ jobId, chapters }: Props) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const [playing, setPlaying] = useState(false);
  const [time, setTime] = useState(0);
  const [duration, setDuration] = useState(0);

  // Active chapter follows the playhead: the last chapter whose start
  // we've passed. -1 before metadata loads.
  let active = -1;
  for (let i = 0; i < chapters.length; i++) {
    if (time >= chapters[i].start - 0.25) active = i;
    else break;
  }

  useEffect(() => {
    if (active < 0 || !listRef.current) return;
    const row = listRef.current.children[active] as HTMLElement | undefined;
    if (!row) return;
    const smooth = !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    row.scrollIntoView({ block: "nearest", behavior: smooth ? "smooth" : "auto" });
  }, [active]);

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
    a.play();
  }

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
      </div>

      {chapters.length > 0 && (
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
      )}
    </div>
  );
}
