"use client";

import { useEffect, useRef, useState } from "react";
import { fetchJob, type Job } from "./api";

// Poll a job until it reaches a terminal state. setTimeout chain (not
// setInterval) so a slow response never stacks requests.
export function useJob(id: string | null, intervalMs = 1500) {
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!id) return;
    let alive = true;

    async function tick() {
      try {
        const j = await fetchJob(id!);
        if (!alive) return;
        setJob(j);
        setError(null);
        if (j.status === "done" || j.status === "error" || j.status === "cancelled") return;
      } catch (e) {
        if (!alive) return;
        setError(e instanceof Error ? e.message : String(e));
      }
      timer.current = setTimeout(tick, intervalMs);
    }

    tick();
    return () => {
      alive = false;
      if (timer.current) clearTimeout(timer.current);
    };
  }, [id, intervalMs]);

  return { job, error };
}
