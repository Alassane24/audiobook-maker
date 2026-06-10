// Typed client for the FastAPI backend. All URLs are relative: in dev,
// next.config.ts proxies them to :8765; in production FastAPI itself
// serves the exported frontend, so same-origin just works.

export type JobStatus = "queued" | "running" | "paused" | "done" | "error" | "cancelled";
export type JobPhase = "detect" | "extract" | "ocr" | "tts" | "mux" | "done";

export interface ChapterInfo {
  title: string;
  start: number; // seconds into the book
}

export interface Job {
  id: string;
  name: string;
  base: string;
  voice: string;
  speed: number;
  bitrate: string;
  status: JobStatus;
  created: string;
  phase?: JobPhase;
  frac?: number; // 0..1 unified forward-only progress
  message?: string;
  mode?: "ocr" | "text";
  chapters_total?: number;
  chapters_info?: ChapterInfo[];
  minutes?: number;
  error?: string;
}

export interface JobSummary {
  id: string;
  name: string;
  status: JobStatus;
  frac: number;
  phase?: JobPhase;
  minutes?: number;
  created: string;
}

export async function fetchJob(id: string): Promise<Job> {
  const r = await fetch(`/api/job/${encodeURIComponent(id)}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`Job not found (${r.status})`);
  return r.json();
}

export async function fetchJobs(): Promise<JobSummary[]> {
  const r = await fetch("/api/jobs", { cache: "no-store" });
  if (!r.ok) throw new Error(`Job list failed (${r.status})`);
  return r.json();
}

export async function deleteJob(id: string): Promise<void> {
  await fetch(`/api/job/${encodeURIComponent(id)}/delete`, { method: "POST" });
}

export async function pauseJob(id: string): Promise<void> {
  await fetch(`/api/job/${encodeURIComponent(id)}/pause`, { method: "POST" });
}

export async function resumeJob(id: string): Promise<void> {
  await fetch(`/api/job/${encodeURIComponent(id)}/resume`, { method: "POST" });
}

export interface BookTextResponse {
  chapters?: { title: string; text: string; images?: { char: number; file: string }[] }[];
  timing?: ([number, number][] | null)[] | null;
  building?: boolean;
  progress?: number;
  message?: string;
  error?: string;
}

// 200 = text ready; 202 = one-time rebuild running (poll again);
// anything else throws.
export async function fetchJobText(id: string): Promise<BookTextResponse> {
  const r = await fetch(`/api/job/${encodeURIComponent(id)}/text`, { cache: "no-store" });
  if (r.status === 200 || r.status === 202) return r.json();
  let detail = "";
  try { detail = (await r.json()).error ?? ""; } catch { /* not json */ }
  throw new Error(detail || `Text unavailable (${r.status})`);
}

export interface UploadOptions {
  file: File;
  voice: string;
  speed: number;
  quality: "compact" | "standard" | "high";
  ambiance: "" | "rain" | "fire";
  ambVol: number;
  onProgress?: (pct: number) => void;
}

// XHR instead of fetch: upload progress events. Epubs can be 100MB+ when
// image-based, so the user needs to see the transfer moving.
export function uploadEpub(opts: UploadOptions): Promise<{ id: string }> {
  return new Promise((resolve, reject) => {
    const form = new FormData();
    form.append("file", opts.file);
    form.append("voice", opts.voice);
    form.append("speed", String(opts.speed));
    form.append("quality", opts.quality);
    form.append("ambiance", opts.ambiance);
    form.append("amb_vol", String(opts.ambVol));

    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/upload");
    xhr.responseType = "json";
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && opts.onProgress) opts.onProgress(Math.round((e.loaded / e.total) * 100));
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300 && xhr.response?.id) resolve(xhr.response);
      else reject(new Error(`Upload failed (${xhr.status})`));
    };
    xhr.onerror = () => reject(new Error("Upload failed — is the server running?"));
    xhr.send(form);
  });
}

export function fmtTime(s: number): string {
  if (!isFinite(s) || s < 0) s = 0;
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = Math.floor(s % 60);
  const mm = h > 0 ? String(m).padStart(2, "0") : String(m);
  return `${h > 0 ? h + ":" : ""}${mm}:${String(sec).padStart(2, "0")}`;
}

// Friendly stage label shown under the progress bar — mirrors the phases
// the pipeline reports, in reading-person words rather than pipeline jargon.
export function phaseLabel(j: Job): string {
  if (j.status === "done") return "";
  switch (j.phase) {
    case "ocr": return "Reading scanned pages";
    case "extract": return "Reading the text";
    case "tts": return "Narrating";
    case "mux": return "Finishing up";
    case "detect": return "Preparing…";
    default: return "";
  }
}
