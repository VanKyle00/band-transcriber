"use client";

import { useEffect, useRef, useState } from "react";

import type { Job } from "@/lib/types";
import StemPanel from "./StemPanel";

// Friendly, real-stage-driven steps for the warm loading screen. Keys match the
// stage strings the pipeline writes (downloading/separating/transcribing); the
// "at" values place each step on the progress bar.
const STEPS = [
  { key: "downloading", label: "Fetching the audio", at: 30 },
  { key: "separating", label: "Separating the instruments", at: 65 },
  { key: "transcribing", label: "Writing out the notes & tabs", at: 95 },
] as const;

// The backend reports discrete stages, not a percentage, so we map each stage to a
// point on the bar and let CSS ease between them — an estimate, not a precise meter.
const PROGRESS: Record<string, number> = {
  queued: 6,
  downloading: 18,
  separating: 50,
  transcribing: 82,
  done: 100,
};

export default function JobView({ jobId }: { jobId: string }) {
  const [job, setJob] = useState<Job | null>(null);
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

  if (job?.status === "error") {
    return (
      <>
        <h1>Something went wrong</h1>
        <div className="card error">{job.error || "Unknown error."}</div>
      </>
    );
  }

  if (job?.status === "done") {
    return (
      <>
        <h1>Your transcription</h1>
        <p className="lede">Job {jobId}</p>
        {job.artifacts?.stems?.map((stem) => <StemPanel key={stem.name} stem={stem} />)}
      </>
    );
  }

  // Still working (no job yet, queued, or processing) → warm, friendly loading screen.
  const base = job?.stage?.split(":")[0] ?? "queued";
  const sub = job?.stage?.includes(":") ? job.stage.split(":")[1] : "";
  const progress = PROGRESS[base] ?? 6;
  const activeStep = STEPS.find((s) => progress < s.at);
  const subLabel = sub ? ` · ${sub.charAt(0).toUpperCase()}${sub.slice(1)}` : "";
  const title = activeStep
    ? `${activeStep.label}${activeStep.key === base ? subLabel : ""}…`
    : "Almost there…";

  return (
    <div className="bt-load">
      <span className="bt-load-decor bt-load-blob1" />
      <span className="bt-load-decor bt-load-blob2" />
      <div className="bt-load-inner">
        <div className="bt-load-record">
          <div className="bt-load-disc" />
          <div className="bt-load-dot" />
          <div className="bt-load-flower">🌼</div>
        </div>
        <div className="bt-load-job">JOB {jobId}</div>
        <h1 className="bt-load-title">{title}</h1>
        <p className="bt-load-copy">
          Hang tight — I’m pulling apart every instrument and writing down the notes. Grab a
          drink, this usually takes a minute or two. ☕
        </p>
        <div className="bt-load-prog">
          <div className="bt-load-bar">
            <div className="bt-load-bar-fill" style={{ width: `${progress}%` }} />
          </div>
          <div className="bt-load-pct">{progress}%</div>
          <div className="bt-load-steps">
            {STEPS.map((s) => {
              const done = progress >= s.at;
              const active = !done && s === activeStep;
              return (
                <div key={s.key} className={`bt-load-step ${done ? "done" : active ? "active" : ""}`}>
                  <span className="bt-load-step-ic">{done ? "✓" : active ? "♪" : "·"}</span>
                  <span className="bt-load-step-lb">{s.label}</span>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
