"use client";

import { useEffect, useState } from "react";
import { VOICES } from "@/lib/voices";
import { previewAudio } from "@/lib/preview-audio";
import { PauseIcon, PlayIcon } from "./icons";

interface Props {
  selected: string;
  onSelect: (id: string) => void;
  speed: number;
}

export function VoiceGallery({ selected, onSelect, speed }: Props) {
  const [playing, setPlaying] = useState<string | null>(null);

  // Live tempo preview: dragging the speed slider re-paces the sample
  // mid-playback (pitch preserved), same as the final narration.
  useEffect(() => previewAudio.setSpeed(speed), [speed]);
  useEffect(() => () => previewAudio.stopAll(), []);

  function togglePreview(id: string) {
    if (playing === id) {
      previewAudio.stopVoice();
      setPlaying(null);
      return;
    }
    previewAudio.playVoice(id, speed, () => setPlaying(null));
    setPlaying(id);
  }

  return (
    <div className="voice-grid" role="radiogroup" aria-label="Narrator voice">
      {VOICES.map((v) => {
        const isSel = v.id === selected;
        const isPlaying = playing === v.id;
        return (
          <div
            key={v.id}
            className={`voice-card${isSel ? " sel" : ""}`}
            role="radio"
            aria-checked={isSel}
            tabIndex={0}
            onClick={() => onSelect(v.id)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onSelect(v.id);
              }
            }}
          >
            <button
              type="button"
              className={`roundel${isPlaying ? " playing" : ""}`}
              aria-label={isPlaying ? `Stop ${v.name} preview` : `Preview ${v.name}`}
              onClick={(e) => {
                e.stopPropagation();
                togglePreview(v.id);
              }}
            >
              {isPlaying ? <PauseIcon /> : <PlayIcon style={{ marginLeft: 2 }} />}
            </button>
            <div className="voice-meta">
              <div className="voice-name">{v.name}</div>
              <div className="voice-tag">{v.tag}</div>
              <div className="voice-desc">{v.desc}</div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
