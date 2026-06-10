import { Suspense } from "react";
import { HeaderBar } from "@/components/header-bar";
import { JobMonitor } from "@/components/job-monitor";

// The job id arrives as ?id=… (static export can't pre-render unknown
// dynamic segments), and useSearchParams requires a Suspense boundary.
export default function JobPage() {
  return (
    <>
      <HeaderBar />
      <Suspense
        fallback={
          <div className="card reveal">
            <p className="empty-note">Loading…</p>
          </div>
        }
      >
        <JobMonitor />
      </Suspense>
    </>
  );
}
