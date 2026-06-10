"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { deleteJob, fetchJobs, type JobSummary } from "@/lib/api";
import { TrashIcon } from "./icons";

const TAG_CLASS: Record<string, string> = {
  done: "ok",
  error: "err",
  running: "run",
  paused: "paused",
};

function statusText(j: JobSummary): string {
  if (j.status === "running") return `${Math.round((j.frac || 0) * 100)}%`;
  return j.status;
}

export function RecentJobs() {
  const [jobs, setJobs] = useState<JobSummary[] | null>(null);

  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;

    async function tick() {
      try {
        const list = await fetchJobs();
        if (alive) setJobs(list);
      } catch {
        if (alive) setJobs((prev) => prev ?? []);
      }
      // Keep the list live while anything is rendering, lazily otherwise.
      timer = setTimeout(tick, 4000);
    }

    tick();
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, []);

  async function remove(id: string) {
    if (!confirm("Stop and delete this audiobook job?")) return;
    await deleteJob(id);
    setJobs((prev) => (prev ? prev.filter((j) => j.id !== id) : prev));
  }

  return (
    <section className="card reveal" style={{ "--d": "0.5s" } as React.CSSProperties}>
      <h2 className="section-label"><span className="numeral">IV</span>The Library</h2>
      {jobs === null ? (
        <p className="empty-note">Loading…</p>
      ) : jobs.length === 0 ? (
        <p className="empty-note">No audiobooks yet — your library awaits its first pressing.</p>
      ) : (
        <div>
          {jobs.map((j) => (
            <div className="job-row" key={j.id}>
              <Link href={`/job?id=${j.id}`} style={{ flex: 1, minWidth: 0, fontWeight: 400 }}>
                <div className="job-title">{j.name}</div>
                <div className="job-sub">
                  {j.minutes ? `${(j.minutes / 60).toFixed(1)} h · ` : ""}
                  {new Date(j.created).toLocaleDateString(undefined, { month: "short", day: "numeric" })}
                </div>
              </Link>
              <span className={`tag ${TAG_CLASS[j.status] ?? ""}`}>{statusText(j)}</span>
              <button type="button" className="btn-ghost danger" onClick={() => remove(j.id)} aria-label={`Delete ${j.name}`}>
                <TrashIcon />
                Delete
              </button>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
