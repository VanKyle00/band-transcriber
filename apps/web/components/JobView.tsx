"use client";

import { useEffect, useRef, useState } from "react";

import type { Job } from "@/lib/types";
import StemPanel from "./StemPanel";

const STAGES = [
  { key: "downloading", label: "Fetching audio" },
  { key: "separating", label: "Separating stems" },
  { key: "transcribing", label: "Transcribing & engraving" },
  { key: "done", label: "Done" },
];

function stageIndex(stage?: string): number {
  if (!stage) return -1;
  const base = stage.split(":")[0];
  return STAGES.findIndex((s) => s.key === base);
}

export default function JobView({ jobId }: { jobId: string }) {
  const [job, setJob] = useState<Job | null>(null);
  const [failed, setFailed] = useState(false);
  const stop = useRef(false);

  useEffect(() => {
    stop.current = false;
    async function tick() {
      try {
        const res = await fetch(`/api/jobs/${jobId}`, { cache: "no-store" });
        if (res.ok) {
          const data: Job = await res.json();
          if (stop.current) return;
          setJob(data);
          if (data.status === "done" || data.status === "error") return;
        }
      } catch {
        /* transient — keep polling */
      }
      if (!stop.current) setTimeout(tick, 3000);
    }
    tick();
    return () => {
      stop.current = true;
    };
  }, [jobId]);

  if (!job) {
    return (
      <>
        <h1>Working…</h1>
        <p className="lede">Job {jobId}</p>
        <div className="card">Loading status…</div>
      </>
    );
  }

  if (job.status === "error") {
    return (
      <>
        <h1>Something went wrong</h1>
        <div className="card error">{job.error || "Unknown error."}</div>
      </>
    );
  }

  const done = job.status === "done";
  const current = stageIndex(job.stage);

  return (
    <>
      <h1>{done ? "Your transcription" : "Processing…"}</h1>
      <p className="lede">Job {jobId}</p>

      {!done && (
        <div className="card">
          <ul className="stage-list">
            {STAGES.map((s, i) => (
              <li key={s.key} className={i < current ? "done" : i === current ? "active" : ""}>
                {i < current ? "✓ " : i === current ? "→ " : "• "}
                {s.label}
              </li>
            ))}
          </ul>
        </div>
      )}

      {done &&
        job.artifacts?.stems?.map((stem) => <StemPanel key={stem.name} stem={stem} />)}
    </>
  );
}
