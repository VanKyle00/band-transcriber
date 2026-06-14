"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { ALL_STEMS } from "@/lib/types";

export default function SubmitForm() {
  const router = useRouter();
  const [mode, setMode] = useState<"file" | "url">("file");
  const [url, setUrl] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [stems, setStems] = useState<string[]>([...ALL_STEMS]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  function toggle(stem: string) {
    setStems((prev) =>
      prev.includes(stem) ? prev.filter((s) => s !== stem) : [...prev, stem],
    );
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    if (stems.length === 0) return setErr("Pick at least one stem.");

    const fd = new FormData();
    fd.set("stems", stems.join(","));
    if (mode === "file") {
      if (!file) return setErr("Choose an audio file.");
      fd.set("file", file);
    } else {
      if (!url.trim()) return setErr("Paste a YouTube/audio URL.");
      fd.set("url", url.trim());
    }

    setBusy(true);
    try {
      // Post directly to the Modal endpoint when configured, so large uploads bypass
      // Vercel's 4.5 MB request-body cap (the /api/jobs proxy is the local-dev fallback).
      const base = process.env.NEXT_PUBLIC_MODAL_WEB_URL;
      const endpoint = base ? `${base}/jobs` : "/api/jobs";
      const res = await fetch(endpoint, { method: "POST", body: fd });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || data.detail || "Submission failed.");
      router.push(`/jobs/${data.job_id}`);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  }

  return (
    <form className="card" onSubmit={submit}>
      <div className="tabs">
        <button type="button" className={mode === "file" ? "active" : ""} onClick={() => setMode("file")}>
          Upload file
        </button>
        <button type="button" className={mode === "url" ? "active" : ""} onClick={() => setMode("url")}>
          YouTube / URL
        </button>
      </div>

      {mode === "file" ? (
        <label className="dropzone">
          {file ? <strong>{file.name}</strong> : "Click to choose an audio file (mp3, wav, m4a…)"}
          <input
            type="file"
            accept="audio/*,video/*"
            style={{ display: "none" }}
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
        </label>
      ) : (
        <input
          type="url"
          placeholder="https://www.youtube.com/watch?v=…"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
        />
      )}

      <div className="stem-toggles">
        {ALL_STEMS.map((s) => (
          <label key={s}>
            <input type="checkbox" checked={stems.includes(s)} onChange={() => toggle(s)} />
            {s}
            {(s === "guitar" || s === "piano") && <span className="badge">experimental</span>}
          </label>
        ))}
      </div>

      {err && <p className="error">{err}</p>}

      <button className="primary" disabled={busy}>
        {busy ? "Submitting…" : "Transcribe"}
      </button>
      <p className="muted" style={{ marginTop: 12, fontSize: 13 }}>
        Tracks are capped at 8 minutes. YouTube links may fail if the video blocks server
        downloads — uploading the file is the most reliable path.
      </p>
    </form>
  );
}
