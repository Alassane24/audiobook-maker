"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { uploadEpub } from "@/lib/api";
import { AMBIANCES, DEFAULT_VOICE, QUALITIES } from "@/lib/voices";
import { previewAudio } from "@/lib/preview-audio";
import { VoiceGallery } from "./voice-gallery";
import { CheckCircleIcon, PlayIcon, UploadIcon } from "./icons";

function fmtSize(bytes: number): string {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function UploadStudio() {
  const router = useRouter();
  const fileInput = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [voice, setVoice] = useState(DEFAULT_VOICE);
  const [speed, setSpeed] = useState(1.0);
  const [ambiance, setAmbiance] = useState<"" | "rain" | "fire">("");
  const [ambVol, setAmbVol] = useState(10);
  const [quality, setQuality] = useState<"compact" | "standard" | "high">("standard");
  const [uploadPct, setUploadPct] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const uploading = uploadPct !== null;

  function acceptFile(f: File | undefined) {
    if (!f) return;
    if (!f.name.toLowerCase().endsWith(".epub") && !f.name.toLowerCase().endsWith(".pdf")) {
      setError("Please upload an .epub or .pdf file.");
      return;
    }
    setError(null);
    setFile(f);
  }

  function pickAmbiance(id: "" | "rain" | "fire") {
    setAmbiance(id);
    // Loop the ambiance immediately, under any playing voice sample —
    // the same layering mux_m4b bakes into the finished book.
    previewAudio.playAmbiance(id, ambVol);
  }

  function changeAmbVol(v: number) {
    setAmbVol(v);
    previewAudio.setAmbianceVolume(v);
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!file || uploading) return;
    previewAudio.stopAll();
    setError(null);
    setUploadPct(0);
    try {
      const { id } = await uploadEpub({ file, voice, speed, quality, ambiance, ambVol, onProgress: setUploadPct });
      router.push(`/job?id=${id}`);
    } catch (err) {
      setUploadPct(null);
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  const speedFill = ((speed - 0.5) / 1.5) * 100;

  return (
    <form onSubmit={submit} className="upload-form">
      <section className="card ornate reveal" style={{ "--d": "0.2s" } as React.CSSProperties}>
        <h2 className="section-label"><span className="numeral">I</span>The Manuscript</h2>
        <label
          className={`drop${dragOver ? " over" : ""}${file ? " has" : ""}`}
          onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={(e) => { e.preventDefault(); setDragOver(false); }}
          onDrop={(e) => {
            e.preventDefault();
            setDragOver(false);
            acceptFile(e.dataTransfer.files?.[0]);
          }}
        >
          {file ? (
            <span className="file-pill">
              <CheckCircleIcon style={{ color: "var(--primary)", flex: "none" }} />
              <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{file.name}</span>
              <span className="size">{fmtSize(file.size)}</span>
            </span>
          ) : (
            <>
              <UploadIcon />
              <span style={{ fontWeight: 600 }}>Choose an .epub or .pdf file</span>
              <span style={{ fontSize: 12, fontWeight: 400, opacity: 0.7 }}>or drag and drop it here</span>
            </>
          )}
          <input
            ref={fileInput}
            type="file"
            accept=".epub,.pdf"
            style={{ display: "none" }}
            onChange={(e) => acceptFile(e.target.files?.[0])}
          />
        </label>
      </section>

      <section className="card ornate reveal" style={{ "--d": "0.3s" } as React.CSSProperties}>
        <h2 className="section-label"><span className="numeral">II</span>The Narrator</h2>
        <p className="field-label" style={{ marginTop: 0 }}>Tap play to audition · speed applies live</p>
        <VoiceGallery selected={voice} onSelect={setVoice} speed={speed} />

        <p className="field-label" style={{ marginTop: 30 }}>Narration speed</p>
        <div className="slider-row">
          <input
            type="range"
            min={0.5}
            max={2}
            step={0.1}
            value={speed}
            aria-label="Narration speed"
            style={{ "--fill": `${speedFill}%` } as React.CSSProperties}
            onChange={(e) => setSpeed(parseFloat(e.target.value))}
          />
          <span className="slider-value">{speed.toFixed(1)}&times;</span>
        </div>
      </section>

      <section className="card ornate reveal" style={{ "--d": "0.4s" } as React.CSSProperties}>
        <h2 className="section-label"><span className="numeral">III</span>The Performance</h2>
        <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
          <div style={{ flex: "1 1 200px" }}>
            <p className="field-label">Background ambiance</p>
            <select value={ambiance} aria-label="Background ambiance" onChange={(e) => pickAmbiance(e.target.value as "" | "rain" | "fire")}>
              {AMBIANCES.map((a) => (
                <option key={a.id} value={a.id}>{a.name}</option>
              ))}
            </select>
          </div>
          <div style={{ flex: "1 1 200px" }}>
            <p className="field-label">Ambiance volume</p>
            <div className="slider-row" style={{ padding: "11px 16px" }}>
              <input
                type="range"
                min={0}
                max={100}
                step={5}
                value={ambVol}
                aria-label="Ambiance volume"
                style={{ "--fill": `${ambVol}%` } as React.CSSProperties}
                onChange={(e) => changeAmbVol(parseInt(e.target.value, 10))}
              />
              <span className="slider-value" style={{ minWidth: 44 }}>{ambVol}%</span>
            </div>
          </div>
        </div>

        <p className="field-label" style={{ marginTop: 26 }}>Output quality</p>
        <div className="pills" role="radiogroup" aria-label="Output quality">
          {QUALITIES.map((q) => (
            <button
              key={q.id}
              type="button"
              role="radio"
              aria-checked={quality === q.id}
              className={`pill${quality === q.id ? " sel" : ""}`}
              onClick={() => setQuality(q.id)}
            >
              {q.name}
              <small>{q.hint}</small>
            </button>
          ))}
        </div>

        {error && (
          <p className="banner err" style={{ marginTop: 22, marginBottom: 0 }} role="alert">{error}</p>
        )}

        <button className="btn-gold" type="submit" disabled={!file || uploading} style={{ marginTop: 30 }}>
          <PlayIcon style={{ width: 18, height: 18 }} />
          {uploading ? (uploadPct! < 100 ? `Uploading… ${uploadPct}%` : "Starting…") : "Generate Audiobook"}
        </button>
      </section>
    </form>
  );
}
