import { HeaderBar } from "@/components/header-bar";
import { UploadStudio } from "@/components/upload-studio";
import { RecentJobs } from "@/components/recent-jobs";

export default function Home() {
  return (
    <>
      <HeaderBar />
      <p className="tagline reveal" style={{ "--d": "0.12s" } as React.CSSProperties}>
        Drop in an EPUB or PDF, pick a voice, and get a beautifully narrated audiobook.
      </p>
      <UploadStudio />
      <RecentJobs />
    </>
  );
}
