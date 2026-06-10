"use client";

import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { deleteJob, pauseJob, phaseLabel, resumeJob, type Job } from "@/lib/api";
import { useJob } from "@/lib/use-job";
import { DecoPlayer } from "./deco-player";
import { BackArrowIcon, CheckCircleIcon, DownloadIcon, TrashIcon } from "./icons";

type StepState = "active" | "done" | "pending";

// Map pipeline phase → stepper visual. Mirrors the proven logic from the
// inline UI: a finished step keeps its gold border but loses the glow, so
// the CURRENT step is always unambiguous.
function stepperState(j: Job): { steps: [StepState, StepState, StepState]; track: number } {
  if (j.status === "done") return { steps: ["done", "done", "done"], track: 100 };
  if (j.phase === "mux") return { steps: ["done", "done", "active"], track: 100 };
  if (j.phase === "tts") return { steps: ["done", "active", "pending"], track: 50 };
  return { steps: ["active", "pending", "pending"], track: 0 };
}

const STEP_LABELS = ["Reading", "Narrating", "Finishing"];

export function JobMonitor() {
  const router = useRouter();
  const params = useSearchParams();
  const id = params.get("id");
  const { job, error } = useJob(id);

  if (!id) {
    return (
      <div className="card reveal">
        <p className="banner err">No job specified.</p>
        <Link href="/" className="btn-ghost"><BackArrowIcon /> Back to the studio</Link>
      </div>
    );
  }

  if (error && !job) {
    return (
      <div className="card reveal">
        <p className="banner err" role="alert">{error}</p>
        <Link href="/" className="btn-ghost"><BackArrowIcon /> Back to the studio</Link>
      </div>
    );
  }

  if (!job) {
    return (
      <div className="card reveal">
        <p className="empty-note">Loading…</p>
      </div>
    );
  }

  const { steps, track } = stepperState(job);
  const pct = Math.round((job.frac || 0) * 100);
  const running = job.status === "running" || job.status === "queued";

  async function onDelete() {
    if (!confirm("Stop and delete this job?")) return;
    await deleteJob(id!);
    router.push("/");
  }

  return (
    <>
      <div className="tagline reveal" style={{ "--d": "0.1s", display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" } as React.CSSProperties}>
        <span style={{ fontFamily: "var(--font-display), Georgia, serif", fontSize: 19, color: "var(--text)", overflowWrap: "anywhere" }}>{job.name}</span>
        <span style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          {job.status === "running" && (
            <button type="button" className="btn-ghost warn" onClick={() => pauseJob(id!)}>Pause</button>
          )}
          {job.status === "paused" && (
            <button type="button" className="btn-ghost" onClick={() => resumeJob(id!)}>Resume</button>
          )}
          <button type="button" className="btn-ghost danger" onClick={onDelete}>
            <TrashIcon /> {job.status === "done" ? "Delete" : "Stop / Delete"}
          </button>
        </span>
      </div>

      <div className="card ornate reveal" style={{ "--d": "0.2s" } as React.CSSProperties}>
        <div className="stepper">
          <span className="track" />
          <span className="track-fill" style={{ width: `${track}%` }} />
          {STEP_LABELS.map((label, i) => (
            <span key={label} className={`step ${steps[i]}`}>{label}</span>
          ))}
        </div>

        {job.status === "paused" && (
          <p className="banner paused" role="status">Paused — narration will pick up where it left off.</p>
        )}

        {job.status === "error" ? (
          <p className="banner err" role="alert">{job.message || "Something went wrong."}</p>
        ) : job.status === "done" ? (
          <>
            <p className="banner ok">
              <CheckCircleIcon />
              Finished{job.minutes ? ` — ${(job.minutes / 60).toFixed(1)} hours of narration` : ""}. Copied to Transfer.
            </p>
            <DecoPlayer jobId={job.id} chapters={job.chapters_info ?? []} />
            <a className="btn-gold" href={`/download/${job.id}`} style={{ textDecoration: "none" }}>
              <DownloadIcon /> Download M4B
            </a>
          </>
        ) : (
          <>
            <div className="bignum" aria-live="polite">
              {pct}<span className="pct-sign">%</span>
            </div>
            <div className="status-line">{job.message || "Queued…"}</div>
            <div className="phase-line">{phaseLabel(job)}</div>
            <div className="progress-shell">
              <div className={`progress-fill${running ? " live" : ""}`} style={{ width: `${pct}%` }} />
            </div>
          </>
        )}
      </div>

      <p className="reveal" style={{ "--d": "0.35s" } as React.CSSProperties}>
        <Link href="/" className="btn-ghost"><BackArrowIcon /> Create another audiobook</Link>
      </p>
    </>
  );
}
